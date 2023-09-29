import json
import logging
from datetime import datetime, timedelta
from shutil import rmtree

import requests
from flask import Blueprint
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.registry import FinishedJobRegistry

from asu import __version__
from asu.common import get_redis_client, is_modified

bp = Blueprint("janitor", __name__)


def update_set(config: dict, key: str, *data: list):
    pipeline = get_redis_client(config).pipeline(True)
    pipeline.delete(key)
    pipeline.sadd(key, *data)
    pipeline.execute()


def update_branch(config, branch):
    version_path = branch["path"].format(version=branch["versions"][0])
    targets = list(
        filter(
            lambda t: not t.startswith("."),
            requests.get(
                config["UPSTREAM_URL"] + f"/{version_path}/targets?json-targets"
            ).json(),
        )
    )

    if not targets:
        logging.warning("No targets found for {branch['name']}")
        return

    update_set(config, f"targets:{branch['name']}", *list(targets))

    architectures = set()

    for version in branch["versions"]:
        logging.info(f"Update {branch['name']}/{version}")
        # TODO: ugly
        version_path = branch["path"].format(version=version)
        version_path_abs = config["JSON_PATH"] / version_path
        version_path_abs.mkdir(exist_ok=True, parents=True)

        for target in targets:
            if target_arch := update_target_profiles(config, branch, version, target):
                architectures.add(target_arch)

        overview = {
            "branch": branch["name"],
            "release": version,
            "image_url": config["UPSTREAM_URL"] + f"/{version_path}/targets/{{target}}",
            "profiles": [],
        }

        for profile_file in (version_path_abs / "targets").rglob("**/*.json"):
            if profile_file.stem in ["index", "manifest", "overview"]:
                continue
            profile = json.loads(profile_file.read_text())
            overview["profiles"].append(
                {
                    "id": profile_file.stem,
                    "target": profile["target"],
                    "titles": profile["titles"],
                }
            )
        (version_path_abs / "overview.json").write_text(
            json.dumps(overview, sort_keys=True, separators=(",", ":"))
        )


def update_target_profiles(config, branch: dict, version: str, target: str) -> str:
    """Update available profiles of a specific version

    Args:
        branch(dict): Containing all branch information as defined in BRANCHES
        version(str): Version within branch
        target(str): Target within version
    """
    logging.info(f"{version}/{target}: Update profiles")
    r = get_redis_client(config)
    version_path = branch["path"].format(version=version)

    profiles_url = (
        config["UPSTREAM_URL"] + f"/{version_path}/targets/{target}/profiles.json"
    )

    req = requests.get(profiles_url)

    if req.status_code != 200:
        logging.warning("Couldn't download %s", profiles_url)
        return False

    metadata = req.json()
    profiles = metadata.pop("profiles", {})

    if not is_modified(config, profiles_url):
        logging.debug(f"{version}/{target}: Skip profiles update")
        return metadata["arch_packages"]

    r.hset(f"architecture:{branch['name']}", target, metadata["arch_packages"])

    r.set(
        f"revision:{version}:{target}",
        metadata["version_code"],
    )

    logging.info(f"{version}/{target}: Found {len(profiles)} profiles")

    pipeline = r.pipeline(True)
    pipeline.delete(f"profiles:{branch['name']}:{version}:{target}")

    for profile, data in profiles.items():
        for supported in data.get("supported_devices", []):
            if not r.hexists(f"mapping:{branch['name']}:{version}:{target}", supported):
                logging.info(
                    f"{version}/{target}: Add profile mapping {supported} -> {profile}"
                )
                r.hset(
                    f"mapping:{branch['name']}:{version}:{target}", supported, profile
                )

        pipeline.sadd(f"profiles:{branch['name']}:{version}:{target}", profile)

        profile_path = (
            config["JSON_PATH"] / version_path / "targets" / target / profile
        ).with_suffix(".json")
        profile_path.parent.mkdir(exist_ok=True, parents=True)
        profile_path.write_text(
            json.dumps(
                {
                    **metadata,
                    **data,
                    "id": profile,
                    "build_at": datetime.utcfromtimestamp(
                        int(metadata.get("source_date_epoch", 0))
                    ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )

        data["target"] = target

    pipeline.execute()

    return metadata["arch_packages"]


def update_meta_json(config):
    latest = list(
        map(
            lambda b: b["versions"][0],
            filter(
                lambda b: b.get("enabled"),
                config["BRANCHES"].values(),
            ),
        )
    )

    branches = dict(
        map(
            lambda b: (
                b["name"],
                {
                    **b,
                    "targets": dict(
                        map(
                            lambda a: (a[0].decode(), a[1].decode()),
                            get_redis_client(config)
                            .hgetall(f"architecture:{b['name']}")
                            .items(),
                        )
                    ),
                },
            ),
            filter(
                lambda b: b.get("enabled"),
                config["BRANCHES"].values(),
            ),
        )
    )

    config["OVERVIEW"] = {
        "latest": latest,
        "branches": branches,
        "server": {
            "version": __version__,
            "contact": "mail@aparcar.org",
            "allow_defaults": config["ALLOW_DEFAULTS"],
            "repository_allow_list": config["REPOSITORY_ALLOW_LIST"],
        },
    }

    config["JSON_PATH"].mkdir(exist_ok=True, parents=True)

    (config["JSON_PATH"] / "overview.json").write_text(
        json.dumps(config["OVERVIEW"], indent=2, sort_keys=False, default=str)
    )

    (config["JSON_PATH"] / "branches.json").write_text(
        json.dumps(list(branches.values()), indent=2, sort_keys=False, default=str)
    )

    (config["JSON_PATH"] / "latest.json").write_text(json.dumps({"latest": latest}))


def update(config):
    """Update the data required to run the server

    For this all available profiles for all enabled versions is
    downloaded and stored in the Redis database.
    """

    if not config["BRANCHES"]:
        logging.error("No BRANCHES defined in config, nothing to do, exiting")
        return
    for branch in config["BRANCHES"].values():
        if not branch.get("enabled"):
            logging.info(f"{branch['name']}: Skip disabled branch")
            continue

        logging.info(f"Update {branch['name']}")
        update_branch(config, branch)

    update_meta_json(config)

    Queue(connection=get_redis_client(config)).enqueue_in(
        timedelta(minutes=10),
        update,
        config,
        job_timeout="1m",
    )
