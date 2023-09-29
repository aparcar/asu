import json
import logging
import re
from datetime import datetime
from os import getenv
from pathlib import Path

from podman import PodmanClient
from rq import get_current_job

from asu.common import (
    check_manifest,
    diff_packages,
    fingerprint_pubkey_usign,
    get_container_version_tag,
    get_packages_hash,
    parse_manifest,
    report_error,
    run_container,
)

log = logging.getLogger("rq.worker")
log.setLevel(logging.DEBUG)


def build(req: dict, job=None):
    """Build image request and setup ImageBuilders automatically

    The `request` dict contains properties of the requested image.

    Args:
        request (dict): Contains all properties of requested image
    """
    store_path = Path(req["public_path"]) / "store"
    store_path.mkdir(parents=True, exist_ok=True)
    log.debug(f"Store path: {store_path}")

    job = job or get_current_job()
    job.meta["detail"] = "init"
    job.meta["request"] = req
    job.save_meta()

    log.debug(f"Building {req}")

    podman = PodmanClient().from_env()

    log.debug(f"Podman version: {podman.version()}")

    container_version_tag = get_container_version_tag(req["version"])
    log.debug(
        f"Container version: {container_version_tag} (requested {req['version']})"
    )

    BASE_CONTAINER = "ghcr.io/openwrt/imagebuilder"
    image = (
        f"{BASE_CONTAINER}:{req['target'].replace('/', '-')}-{container_version_tag}"
    )

    log.info(f"Pulling {image}...")
    podman.images.pull(image)
    log.info(f"Pulling {image}... done")

    returncode, job.meta["stdout"], job.meta["stderr"] = run_container(
        podman, image, ["make", "info"]
    )

    job.save_meta()

    version_code = re.search('Current Revision: "(r.+)"', job.meta["stdout"]).group(1)

    if "version_code" in req:
        if version_code != req.get("version_code"):
            report_error(
                job,
                f"Received inncorrect version {version_code} (requested {req['version_code']})",
            )

    default_packages = set(
        re.search(r"Default Packages: (.*)\n", job.meta["stdout"]).group(1).split()
    )
    log.debug(f"Default packages: {default_packages}")

    profile_packages = set(
        re.search(
            r"{}:\n    .+\n    Packages: (.*?)\n".format(req["profile"]),
            job.meta["stdout"],
            re.MULTILINE,
        )
        .group(1)
        .split()
    )

    if req.get("diff_packages"):
        req["build_cmd_packages"] = diff_packages(
            set(req["packages"]), default_packages | profile_packages
        )
        log.debug(f"Diffed packages: {req['build_cmd_packages']}")

    job.meta["imagebuilder_status"] = "calculate_packages_hash"
    job.save_meta()

    mounts = []

    bin_dir = req["request_hash"]
    (store_path / bin_dir / "keys").mkdir(parents=True, exist_ok=True)
    log.debug("Created store path: %s", store_path / bin_dir)

    if "repository_keys" in req:
        log.debug("Found extra keys")

        for key in req.get("repository_keys"):
            fingerprint = fingerprint_pubkey_usign(key)
            log.debug(f"Found key {fingerprint}")

            (store_path / bin_dir / "keys" / fingerprint).write_text(
                f"untrusted comment: {fingerprint}\n{key}"
            )

            mounts.append(
                {
                    "type": "bind",
                    "source": str(store_path / bin_dir / "keys" / fingerprint),
                    "target": "/builder/keys/" + fingerprint,
                    "read_only": True,
                },
            )

    if "repositories" in req:
        log.debug("Found extra repos")
        repositories = ""
        for name, repo in req.get("repositories").items():
            if repo.startswith(tuple(req["repository_allow_list"])):
                repositories += f"src/gz {name} {repo}\n"
            else:
                report_error(job, f"Repository {repo} not allowed")

        repositories += "src imagebuilder file:packages\noption check_signature"

        (store_path / bin_dir / "repositories.conf").write_text(repositories)

        mounts.append(
            {
                "type": "bind",
                "source": str(store_path / bin_dir / "repositories.conf"),
                "target": "/builder/repositories.conf",
                "read_only": True,
            },
        )

    returncode, job.meta["stdout"], job.meta["stderr"] = run_container(
        podman,
        image,
        [
            "make",
            "manifest",
            f"PROFILE={req['profile']}",
            f"PACKAGES={' '.join(sorted(req.get('build_cmd_packages', [])))}",
            "STRIP_ABI=1",
        ],
        mounts=mounts,
    )

    job.save_meta()

    if returncode:
        report_error(job, "Impossible package selection")

    manifest = parse_manifest(job.meta["stdout"])
    log.debug(f"Manifest: {manifest}")

    # Check if all requested packages are in the manifest
    if err := check_manifest(manifest, req.get("packages_versions", {})):
        report_error(job, err)

    packages_hash = get_packages_hash(manifest.keys())
    log.debug(f"Packages Hash: {packages_hash}")

    job.meta["build_cmd"] = [
        "make",
        "image",
        f"PROFILE={req['profile']}",
        f"PACKAGES={' '.join(sorted(req.get('build_cmd_packages', [])))}",
        f"EXTRA_IMAGE_NAME={packages_hash}",
        f"BIN_DIR=/builder/{bin_dir}",
    ]

    # Check if custom rootfs size is requested
    if rootfs_size_mb := req.get("rootfs_size_mb"):
        job.meta["build_cmd"].append(f"ROOTFS_PARTSIZE={rootfs_size_mb}")

    log.debug("Build command: %s", job.meta["build_cmd"])

    job.meta["imagebuilder_status"] = "building_image"
    job.save_meta()

    if req.get("defaults"):
        log.debug("Found defaults")

        defaults_file = store_path / bin_dir / "files/etc/uci-defaults/99-asu-defaults"
        defaults_file.parent.mkdir(parents=True)
        defaults_file.write_text(req["defaults"])
        job.meta["build_cmd"].append(f"FILES={store_path / bin_dir / 'files'}")
        mounts.append(
            {
                "type": "bind",
                "source": str(store_path / bin_dir / "files"),
                "target": str(store_path / bin_dir / "files"),
                "read_only": True,
            },
        )

    returncode, job.meta["stdout"], job.meta["stderr"] = run_container(
        podman,
        image,
        job.meta["build_cmd"],
        mounts=mounts,
        copy=["/builder/" + bin_dir, store_path],
    )

    job.save_meta()

    if returncode:
        report_error(job, "Error while building firmware. See stdout/stderr")

    if "is too big" in job.meta["stderr"]:
        report_error(job, "Selected packages exceed device storage")

    json_file = store_path / bin_dir / "profiles.json"

    if not json_file.is_file():
        report_error(job, "No JSON file found")

    json_content = json.loads(json_file.read_text())

    # Check if profile is in JSON file
    if req["profile"] not in json_content["profiles"]:
        report_error(job, "Profile not found in JSON file")

    # get list of installable images to sign (i.e. don't sign kernel)
    images = list(
        map(
            lambda i: i["name"],
            filter(
                lambda i: i["type"]
                in ["sysupgrade", "factory", "combined", "combined-efi"],
                json_content["profiles"][req["profile"]]["images"],
            ),
        )
    )

    log.info(f"Signing images: {images}")

    # job.meta["imagebuilder_status"] = "signing_images"
    job.save_meta()

    build_key = getenv("BUILD_KEY") or str(Path.cwd() / "key-build")

    if Path(build_key).is_file():
        log.info(f"Signing images with key {build_key}")
        returncode, job.meta["stdout"], job.meta["stderr"] = run_container(
            podman,
            image,
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
                    "source": str(store_path / bin_dir),
                    "target": str(store_path / bin_dir),
                    "read_only": False,
                },
            ],
            user="root",  # running as root to have write access to the mounted volume
            working_dir=str(store_path / bin_dir),
            environment={
                "IMAGES_TO_SIGN": " ".join(images),
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/builder/staging_dir/host/bin",
            },
        )
        job.save_meta()

    else:
        log.warning("No build key found, skipping signing")

    json_content.update({"manifest": manifest})
    json_content.update(json_content["profiles"][req["profile"]])
    json_content["id"] = req["profile"]
    json_content["bin_dir"] = str(bin_dir)
    json_content.pop("profiles")
    json_content["build_at"] = datetime.utcfromtimestamp(
        int(json_content.get("source_date_epoch", 0))
    ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    json_content["detail"] = "done"

    log.debug("JSON content %s", json_content)

    # Increment stats
    job.connection.hincrby(
        "stats:builds",
        "#".join([req["version"], req["target"], req["profile"]]),
    )

    return json_content
