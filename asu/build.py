import json
import logging
import re
from datetime import datetime
from os import getenv
from pathlib import Path
from typing import Union

from rq import get_current_job

from asu.build_request import BuildRequest
from asu.config import settings
from asu.package_changes import appy_package_changes
from asu.util import (
    add_timestamp,
    check_manifest,
    diff_packages,
    fingerprint_pubkey_usign,
    get_branch,
    get_container_version_tag,
    get_packages_hash,
    get_podman,
    get_request_hash,
    parse_manifest,
    report_error,
    run_cmd,
)

log = logging.getLogger("rq.worker")


def build(build_request: BuildRequest, job=None):
    """Build image request and setup ImageBuilders automatically

    The `request` dict contains properties of the requested image.

    Args:
        request (dict): Contains all properties of requested image
    """

    request_hash = get_request_hash(build_request)
    bin_dir: Path = settings.public_path / "store" / request_hash
    bin_dir.mkdir(parents=True, exist_ok=True)
    log.debug(f"Bin dir: {bin_dir}")

    job = job or get_current_job()
    job.meta["detail"] = "init"
    job.meta["imagebuilder_status"] = "init"
    job.meta["request"] = build_request
    job.save_meta()

    log.debug(f"Building {build_request}")

    podman = get_podman()

    log.debug(f"Podman version: {podman.version()}")

    container_version_tag = get_container_version_tag(build_request.version)
    log.debug(
        f"Container version: {container_version_tag} (requested {build_request.version})"
    )

    mounts: list[dict[str, Union[str, bool]]] = []
    environment: dict[str, str] = {}

    image = f"{settings.base_container}:{build_request.target.replace('/', '-')}-{container_version_tag}"

    if build_request.version.lower().endswith("snapshot"):
        environment.update(
            {
                "TARGET": build_request.target,
                "VERSION_PATH": get_branch(build_request.version)
                .get("path", "")
                .replace("{version}", build_request.version),
            }
        )
        if settings.squid_cache:
            environment.update(
                {
                    "use_proxy": "on",
                    "http_proxy": "http://127.0.0.1:3128",
                }
            )

    job.meta["imagebuilder_status"] = "container_setup"
    job.save_meta()

    log.info(f"Pulling {image}...")
    podman.images.pull(image)
    log.info(f"Pulling {image}... done")

    (bin_dir / "keys").mkdir(parents=True, exist_ok=True)
    log.debug("Created store path: %s", bin_dir)

    if build_request.repository_keys:
        log.debug("Found extra keys")

        for key in build_request.repository_keys:
            fingerprint = fingerprint_pubkey_usign(key)
            log.debug(f"Found key {fingerprint}")

            (bin_dir / "keys" / fingerprint).write_text(
                f"untrusted comment: {fingerprint}\n{key}"
            )

            mounts.append(
                {
                    "type": "bind",
                    "source": str(bin_dir / "keys" / fingerprint),
                    "target": "/builder/keys/" + fingerprint,
                    "read_only": True,
                },
            )

    if build_request.repositories:
        log.debug("Found extra repos")
        repositories = ""
        for name, repo in build_request.repositories.items():
            if repo.startswith(tuple(settings.repository_allow_list)):
                repositories += f"src/gz {name} {repo}\n"
            else:
                report_error(job, f"Repository {repo} not allowed")

        repositories += "src imagebuilder file:packages\noption check_signature"

        (bin_dir / "repositories.conf").write_text(repositories)

        mounts.append(
            {
                "type": "bind",
                "source": str(bin_dir / "repositories.conf"),
                "target": "/builder/repositories.conf",
                "read_only": True,
            },
        )

    if build_request.defaults:
        log.debug("Found defaults")

        defaults_file = bin_dir / "files/etc/uci-defaults/99-asu-defaults"
        defaults_file.parent.mkdir(parents=True)
        defaults_file.write_text(build_request.defaults)
        mounts.append(
            {
                "type": "bind",
                "source": str(bin_dir / "files"),
                "target": str(bin_dir / "files"),
                "read_only": True,
            },
        )

    log.debug("Mounts: %s", mounts)

    container = podman.containers.create(
        image,
        command=["sleep", "600"],
        mounts=mounts,
        cap_drop=["all"],
        no_new_privileges=True,
        privileged=False,
        networks={"pasta": {}},
        auto_remove=True,
        environment=environment,
    )
    container.start()

    if build_request.version.lower().endswith("snapshot"):
        log.debug("Setting up ImageBuilder")
        returncode, job.meta["stdout"], job.meta["stderr"] = run_cmd(
            container, ["sh", "setup.sh"]
        )

    returncode, job.meta["stdout"], job.meta["stderr"] = run_cmd(
        container, ["make", "info"]
    )

    job.meta["imagebuilder_status"] = "validate_revision"
    job.save_meta()

    version_code = re.search('Current Revision: "(r.+)"', job.meta["stdout"]).group(1)

    if requested := build_request.version_code:
        if version_code != requested:
            report_error(
                job,
                f"Received incorrect version {version_code} (requested {requested})",
            )

    default_packages = set(
        re.search(r"Default Packages: (.*)\n", job.meta["stdout"]).group(1).split()
    )
    log.debug(f"Default packages: {default_packages}")

    profile_packages = set(
        re.search(
            r"{}:\n    .+\n    Packages: (.*?)\n".format(build_request.profile),
            job.meta["stdout"],
            re.MULTILINE,
        )
        .group(1)
        .split()
    )

    appy_package_changes(build_request)

    build_cmd_packages = build_request.packages

    if build_request.diff_packages:
        build_cmd_packages: list[str] = diff_packages(
            build_request.packages, default_packages | profile_packages
        )
        log.debug(f"Diffed packages: {build_cmd_packages}")

    job.meta["imagebuilder_status"] = "validate_manifest"
    job.save_meta()

    returncode, job.meta["stdout"], job.meta["stderr"] = run_cmd(
        container,
        [
            "make",
            "manifest",
            f"PROFILE={build_request.profile}",
            f"PACKAGES={' '.join(build_cmd_packages)}",
            "STRIP_ABI=1",
        ],
    )

    job.save_meta()

    if returncode:
        report_error(job, "Impossible package selection")

    manifest: dict[str, str] = parse_manifest(job.meta["stdout"])
    log.debug(f"Manifest: {manifest}")

    # Check if all requested packages are in the manifest
    if err := check_manifest(manifest, build_request.packages_versions):
        report_error(job, err)

    packages_hash: str = get_packages_hash(manifest.keys())
    log.debug(f"Packages Hash: {packages_hash}")

    job.meta["build_cmd"] = [
        "make",
        "image",
        f"PROFILE={build_request.profile}",
        f"PACKAGES={' '.join(build_cmd_packages)}",
        f"EXTRA_IMAGE_NAME={packages_hash[:12]}",
        f"BIN_DIR=/builder/{request_hash}",
    ]

    if build_request.defaults:
        job.meta["build_cmd"].append(f"FILES={bin_dir}/files")

    # Check if custom rootfs size is requested
    if build_request.rootfs_size_mb:
        log.debug("Found custom rootfs size %d", build_request.rootfs_size_mb)
        job.meta["build_cmd"].append(f"ROOTFS_PARTSIZE={build_request.rootfs_size_mb}")

    log.debug("Build command: %s", job.meta["build_cmd"])

    job.meta["imagebuilder_status"] = "building_image"
    job.save_meta()

    returncode, job.meta["stdout"], job.meta["stderr"] = run_cmd(
        container,
        job.meta["build_cmd"],
        copy=["/builder/" + request_hash, bin_dir.parent],
    )

    container.kill()

    job.save_meta()

    if any(err in job.meta["stderr"] for err in ["is too big", "out of space?"]):
        report_error(job, "Selected packages exceed device storage")

    if returncode:
        report_error(job, "Error while building firmware. See stdout/stderr")

    json_file = bin_dir / "profiles.json"

    if not json_file.is_file():
        report_error(job, "No JSON file found")

    json_content = json.loads(json_file.read_text())

    # Check if profile is in JSON file
    if build_request.profile not in json_content["profiles"]:
        report_error(job, "Profile not found in JSON file")

    # get list of installable images to sign (i.e. don't sign kernel)
    images = list(
        map(
            lambda i: i["name"],
            filter(
                lambda i: i["type"]
                in ["sysupgrade", "factory", "combined", "combined-efi", "sdcard"],
                json_content["profiles"][build_request.profile]["images"],
            ),
        )
    )

    log.info(f"Signing images: {images}")

    # job.meta["imagebuilder_status"] = "signing_images"
    job.save_meta()

    build_key = getenv("BUILD_KEY") or str(Path.cwd() / "key-build")

    if Path(build_key).is_file():
        log.info(f"Signing images with key {build_key}")
        container = podman.containers.create(
            image,
            mounts=[
                {
                    "type": "bind",
                    "source": build_key,
                    "target": "/builder/key-build",
                    "read_only": True,
                },
                {
                    "type": "bind",
                    "source": build_key + ".ucert",
                    "target": "/builder/key-build.ucert",
                    "read_only": True,
                },
                {
                    "type": "bind",
                    "source": str(bin_dir),
                    "target": request_hash,
                    "read_only": False,
                },
            ],
            user="root",  # running as root to have write access to the mounted volume
            working_dir=request_hash,
            environment={
                "IMAGES_TO_SIGN": " ".join(images),
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/builder/staging_dir/host/bin",
            },
            auto_remove=True,
        )
        returncode, job.meta["stdout"], job.meta["stderr"] = run_cmd(
            container,
            [
                "bash",
                "-c",
                (
                    "env;"
                    "for IMAGE in $IMAGES_TO_SIGN; do "
                    "touch ${IMAGE}.test;"
                    'fwtool -t -s /dev/null "$IMAGE" && echo "sign entfern";'
                    'cp "/builder/key-build.ucert" "$IMAGE.ucert" && echo "moved";'
                    'usign -S -m "$IMAGE" -s "/builder/key-build" -x "$IMAGE.sig"  && echo "usign";'
                    'ucert -A -c "$IMAGE.ucert" -x "$IMAGE.sig" && echo "ucert";'
                    'fwtool -S "$IMAGE.ucert" "$IMAGE" && echo "fwtool";'
                    "done"
                ),
            ],
        )
        container.stop()
        job.save_meta()
    else:
        log.warning("No build key found, skipping signing")

    json_content.update({"manifest": manifest})
    json_content.update(json_content["profiles"][build_request.profile])
    json_content["id"] = build_request.profile
    json_content["bin_dir"] = request_hash
    json_content["build_cmd_packages"] = build_cmd_packages
    json_content.pop("profiles")
    json_content["build_at"] = datetime.utcfromtimestamp(
        int(json_content.get("source_date_epoch", 0))
    ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    json_content["detail"] = "done"

    log.debug("JSON content %s", json_content)

    add_timestamp(
        f"stats:builds:{build_request.version}:{build_request.target}:{build_request.profile}",
        {
            "stats": "builds",
            "version": build_request.version,
            "target": build_request.target,
            "profile": build_request.profile,
        },
    )

    job.meta["imagebuilder_status"] = "done"
    job.save_meta()

    return json_content
