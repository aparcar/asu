import datetime
import json
import logging
import re
import shutil
import tarfile
from io import BytesIO
from os import getenv
from pathlib import Path
from typing import Union
from time import perf_counter

from rq import get_current_job
from podman import errors
from rq.utils import parse_timeout

from asu.build_request import BuildRequest
from asu.config import settings
from asu.package_changes import apply_package_changes
from asu.repositories import (
    merge_repositories,
    validate_repos,
)
from asu.store import LocalStore, get_store
from asu.util import (
    add_timestamp,
    add_build_event,
    check_manifest,
    check_package_errors,
    diff_packages,
    error_log,
    fingerprint_pubkey_usign,
    get_branch,
    get_container_version_tag,
    get_packages_hash,
    get_podman,
    get_request_hash,
    is_snapshot_build,
    parse_manifest,
    report_error,
    run_cmd,
)

log = logging.getLogger("rq.worker")


def _cleanup_container(container):
    """Kill and remove a container with its volumes."""
    try:
        container.kill()
    except Exception:
        pass
    try:
        container.remove(v=True, force=True)
    except Exception as e:
        log.warning(f"Failed to remove container {container.id[:12]}: {e}")


def _make_tar(files: dict[str, str | bytes]) -> bytes:
    """Create an in-memory tar archive from a dict of {path: content}.

    Args:
        files: mapping of archive-relative paths to file contents
               (str will be encoded to utf-8)

    Returns:
        bytes of a tar archive
    """
    buf = BytesIO()
    with tarfile.TarFile(fileobj=buf, mode="w") as tar:
        for name, content in files.items():
            data = content.encode("utf-8") if isinstance(content, str) else content
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, BytesIO(data))
    return buf.getvalue()


def _detect_apk_mode(container) -> bool:
    """Detect whether the ImageBuilder uses apk or opkg.

    Checks for the presence of /builder/repositories (apk) vs
    /builder/repositories.conf (opkg) inside the running container.
    """
    rc, _, _ = run_cmd(container, ["test", "-f", "/builder/repositories"])
    return rc == 0


def inject_files(container, build_request, job=None):
    """Copy keys, repositories, and defaults into a running container.

    Uses put_archive to inject files directly — no bind mounts needed,
    so there are no host-path dependencies.
    """
    if build_request.repository_keys:
        files = {}
        for i, key in enumerate(build_request.repository_keys):
            if key.strip().startswith("-----BEGIN"):
                files[f"keys/custom-{i}.pem"] = key
            else:
                fingerprint = fingerprint_pubkey_usign(key)
                files[f"keys/{fingerprint}"] = (
                    f"untrusted comment: {fingerprint}\n{key}"
                )
        if files:
            container.put_archive("/builder/", _make_tar(files))

    if build_request.repositories:
        allowed = validate_repos(build_request.repositories)
        apk_mode = _detect_apk_mode(container)
        repo_file = "repositories" if apk_mode else "repositories.conf"

        base = ""
        if build_request.repositories_mode == "append":
            _, base, _ = run_cmd(container, ["cat", repo_file])

        merged = merge_repositories(base, allowed, apk_mode)
        container.put_archive("/builder/", _make_tar({repo_file: merged}))

    if build_request.defaults:
        container.put_archive(
            "/builder/",
            _make_tar(
                {"asu-files/etc/uci-defaults/99-asu-defaults": build_request.defaults}
            ),
        )


def _build(build_request: BuildRequest, job=None):
    """Build image request and setup ImageBuilders automatically

    The `request` dict contains properties of the requested image.

    Args:
        request (dict): Contains all properties of requested image
    """

    build_start: float = perf_counter()

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

    environment: dict[str, str] = {}

    image = f"{settings.base_container}:{build_request.target.replace('/', '-')}-{container_version_tag}"

    if is_snapshot_build(build_request.version):
        environment.update(
            {
                "TARGET": build_request.target,
                "VERSION_PATH": get_branch(build_request.version)
                .get("path", "")
                .replace("{version}", build_request.version),
            }
        )

    job.meta["imagebuilder_status"] = "container_setup"
    job.save_meta()

    log.info(f"Pulling {image}...")
    try:
        podman.images.pull(image)
    except errors.ImageNotFound:
        report_error(
            job,
            f"Image not found: {image}. If this version was just released, please try again in a few hours as it may take some time to become fully available.",
        )
    log.info(f"Pulling {image}... done")

    mounts: list[dict[str, Union[str, bool]]] = [
        {"type": "tmpfs", "target": f"/builder/{request_hash}"},
    ]

    container = podman.containers.create(
        image,
        command=["sleep", str(parse_timeout(settings.job_timeout))],
        mounts=mounts,
        cap_drop=["all"],
        no_new_privileges=True,
        privileged=False,
        networks={"asu-build": {}},
        environment=environment,
        image_volume_mode="ignore",
    )
    try:
        container.start()

        if is_snapshot_build(build_request.version):
            log.info("Running setup.sh for ImageBuilder")
            returncode, job.meta["stdout"], job.meta["stderr"] = run_cmd(
                container, ["sh", "setup.sh"]
            )
            if returncode:
                report_error(job, f"Could not set up ImageBuilder ({returncode=})")

        inject_files(container, build_request, job)

        # If upstream_url is HTTP (caching proxy), rewrite repository URLs
        # from https://host/path to http://cache/host/path
        if settings.upstream_url.startswith("http://"):
            cache_host = settings.upstream_url.rstrip("/")
            repo_file = (
                "repositories" if _detect_apk_mode(container) else "repositories.conf"
            )
            run_cmd(
                container,
                ["sed", "-i", f"s|https://|{cache_host}/|g", repo_file],
            )

        returncode, job.meta["stdout"], job.meta["stderr"] = run_cmd(
            container, ["make", "info"]
        )

        job.meta["imagebuilder_status"] = "validate_revision"
        job.save_meta()

        version_code = re.search('Current Revision: "(r.+)"', job.meta["stdout"]).group(
            1
        )

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

        apply_package_changes(build_request)

        extra_packages = (
            set(build_request.packages) - default_packages - profile_packages
        )
        branch = get_branch(build_request.version)["name"]
        for pkg in extra_packages:
            if not pkg.startswith("-"):
                add_timestamp(
                    f"stats:packages:{branch}:{pkg}",
                    {"stats": "packages", "branch": branch, "package": pkg},
                )

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
            report_error(job, check_package_errors(job.meta["stderr"]))

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
            job.meta["build_cmd"].append("FILES=/builder/asu-files")

        # Check if custom rootfs size is requested
        if build_request.rootfs_size_mb:
            log.debug("Found custom rootfs size %d", build_request.rootfs_size_mb)
            job.meta["build_cmd"].append(
                f"ROOTFS_PARTSIZE={build_request.rootfs_size_mb}"
            )

        log.debug("Build command: %s", job.meta["build_cmd"])

        job.meta["imagebuilder_status"] = "building_image"
        job.save_meta()

        returncode, job.meta["stdout"], job.meta["stderr"] = run_cmd(
            container,
            job.meta["build_cmd"],
            copy=["/builder/" + request_hash, bin_dir.parent],
        )
    finally:
        _cleanup_container(container)

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
                lambda i: (
                    i["type"]
                    in ["sysupgrade", "factory", "combined", "combined-efi", "sdcard"]
                ),
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
                    "target": "/work",
                    "read_only": False,
                },
            ],
            user="root",
            working_dir="/work",
            environment={
                "IMAGES_TO_SIGN": " ".join(images),
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/builder/staging_dir/host/bin",
            },
            image_volume_mode="ignore",
        )
        try:
            container.start()
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
        finally:
            _cleanup_container(container)
        job.save_meta()
    else:
        log.warning("No build key found, skipping signing")

    store = get_store()
    store.upload_dir(bin_dir, request_hash)

    if not isinstance(store, LocalStore):
        shutil.rmtree(bin_dir, ignore_errors=True)

    json_content.update({"manifest": manifest})
    json_content.update(json_content["profiles"][build_request.profile])
    json_content["id"] = build_request.profile
    json_content["bin_dir"] = request_hash
    json_content["build_cmd_packages"] = build_cmd_packages
    json_content.pop("profiles")
    json_content["build_at"] = datetime.datetime.fromtimestamp(
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

    # Calculate build duration and log it
    build_duration: float = round(perf_counter() - build_start)
    add_timestamp(
        f"stats:time:{build_request.version}:{build_request.target}:{build_request.profile}",
        {
            "stats": "time",
            "version": build_request.version,
            "target": build_request.target,
            "profile": build_request.profile,
        },
        build_duration,
    )

    job.meta["imagebuilder_status"] = "done"
    job.save_meta()

    return json_content


def build(build_request: BuildRequest, job=None):
    try:
        result = _build(build_request, job)
    except Exception as exc:
        # Log all build errors, including internal server errors.
        add_build_event("failures")
        error_log.log_build_error(build_request, str(exc))
        raise
    else:
        add_build_event("successes")
        return result
