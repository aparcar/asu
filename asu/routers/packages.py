"""Package selection API router.

This router provides endpoints for querying package information and
calculating package selections independently of the build process.
"""

import logging

from fastapi import APIRouter, Response, Request
from pydantic import BaseModel, Field

from asu.build_request import BuildRequest
from asu.package_selection import (
    calculate_package_selection,
)
from asu.routers.api import validate_request
from asu.util import (
    get_branch,
    get_container_version_tag,
    get_podman,
    is_snapshot_build,
    run_cmd,
)

router = APIRouter()
log = logging.getLogger("rq.worker")


class PackageSelectionRequest(BaseModel):
    """Request model for package selection endpoint."""

    version: str
    target: str
    profile: str
    packages: list[str] = Field(default_factory=list)
    diff_packages: bool = False
    packages_versions: dict[str, str] = Field(default_factory=dict)


class PackageSelectionResponse(BaseModel):
    """Response model for package selection endpoint."""

    default_packages: list[str]
    profile_packages: list[str]
    final_packages: list[str]
    packages_to_add: list[str]
    packages_to_remove: list[str]


@router.post("/packages/select")
def api_v1_packages_select(
    request: Request,
    package_request: PackageSelectionRequest,
    response: Response,
):
    """Calculate package selection for a given profile and package list.

    This endpoint determines what packages will be included in a build without
    actually performing the build. It's useful for clients to preview package
    selections before triggering a build.
    """
    # Create a BuildRequest from the package selection request
    build_request = BuildRequest(
        version=package_request.version,
        target=package_request.target,
        profile=package_request.profile,
        packages=package_request.packages,
        diff_packages=package_request.diff_packages,
        packages_versions=package_request.packages_versions,
    )

    # Validate the request
    validation_result, status = validate_request(request.app, build_request)
    if validation_result:
        response.status_code = status
        return validation_result

    # Get ImageBuilder info to extract default and profile packages
    podman = get_podman()
    container_version_tag = get_container_version_tag(build_request.version)

    image = f"ghcr.io/openwrt/imagebuilder:{build_request.target.replace('/', '-')}-{container_version_tag}"

    try:
        podman.images.pull(image)
    except Exception as e:
        response.status_code = 404
        return {
            "detail": f"Image not found: {image}. Error: {str(e)}",
            "status": 404,
        }

    environment = {}
    if is_snapshot_build(build_request.version):
        environment.update(
            {
                "TARGET": build_request.target,
                "VERSION_PATH": get_branch(build_request.version)
                .get("path", "")
                .replace("{version}", build_request.version),
            }
        )

    container = podman.containers.create(
        image,
        command=["sleep", "300"],
        cap_drop=["all"],
        no_new_privileges=True,
        privileged=False,
        networks={"pasta": {}},
        auto_remove=True,
        environment=environment,
    )
    container.start()

    try:
        if is_snapshot_build(build_request.version):
            returncode, stdout, stderr = run_cmd(container, ["sh", "setup.sh"])
            if returncode:
                container.kill()
                response.status_code = 500
                return {
                    "detail": "Could not set up ImageBuilder",
                    "status": 500,
                }

        returncode, stdout, stderr = run_cmd(container, ["make", "info"])

        if returncode:
            container.kill()
            response.status_code = 500
            return {
                "detail": f"Failed to get ImageBuilder info: {stderr}",
                "status": 500,
            }

        # Import here to avoid circular dependency
        from asu.package_selection import (
            get_default_packages,
            get_profile_packages,
        )

        default_packages = get_default_packages(stdout)
        profile_packages = get_profile_packages(stdout, build_request.profile)

        final_packages = calculate_package_selection(
            build_request, default_packages, profile_packages
        )

        # Calculate which packages are being added and removed
        packages_to_add = [p for p in final_packages if not p.startswith("-")]
        packages_to_remove = [
            p.removeprefix("-") for p in final_packages if p.startswith("-")
        ]

        return PackageSelectionResponse(
            default_packages=sorted(default_packages),
            profile_packages=sorted(profile_packages),
            final_packages=final_packages,
            packages_to_add=packages_to_add,
            packages_to_remove=packages_to_remove,
        )
    finally:
        container.kill()


@router.get("/packages/defaults/{version}/{target}/{subtarget}")
def api_v1_packages_defaults(
    version: str,
    target: str,
    subtarget: str,
    response: Response,
) -> dict:
    """Get default packages for a target/subtarget.

    This endpoint retrieves the default packages that are included
    in builds for a specific target/subtarget combination.
    """
    full_target = f"{target}/{subtarget}"

    podman = get_podman()
    container_version_tag = get_container_version_tag(version)

    image = f"ghcr.io/openwrt/imagebuilder:{full_target.replace('/', '-')}-{container_version_tag}"

    try:
        podman.images.pull(image)
    except Exception as e:
        response.status_code = 404
        return {
            "detail": f"Image not found: {image}. Error: {str(e)}",
            "status": 404,
        }

    environment = {}
    if is_snapshot_build(version):
        environment.update(
            {
                "TARGET": full_target,
                "VERSION_PATH": get_branch(version)
                .get("path", "")
                .replace("{version}", version),
            }
        )

    container = podman.containers.create(
        image,
        command=["sleep", "60"],
        cap_drop=["all"],
        no_new_privileges=True,
        privileged=False,
        networks={"pasta": {}},
        auto_remove=True,
        environment=environment,
    )
    container.start()

    try:
        if is_snapshot_build(version):
            returncode, stdout, stderr = run_cmd(container, ["sh", "setup.sh"])
            if returncode:
                container.kill()
                response.status_code = 500
                return {"detail": "Could not set up ImageBuilder", "status": 500}

        returncode, stdout, stderr = run_cmd(container, ["make", "info"])

        if returncode:
            container.kill()
            response.status_code = 500
            return {
                "detail": f"Failed to get ImageBuilder info: {stderr}",
                "status": 500,
            }

        from asu.package_selection import get_default_packages

        default_packages = get_default_packages(stdout)

        return {"packages": sorted(default_packages)}
    finally:
        container.kill()


@router.get("/packages/profile/{version}/{target}/{subtarget}/{profile}")
def api_v1_packages_profile(
    version: str,
    target: str,
    subtarget: str,
    profile: str,
    response: Response,
) -> dict:
    """Get profile-specific packages for a profile.

    This endpoint retrieves the packages that are specific to a particular
    device profile, in addition to the default packages.
    """
    full_target = f"{target}/{subtarget}"

    podman = get_podman()
    container_version_tag = get_container_version_tag(version)

    image = f"ghcr.io/openwrt/imagebuilder:{full_target.replace('/', '-')}-{container_version_tag}"

    try:
        podman.images.pull(image)
    except Exception as e:
        response.status_code = 404
        return {
            "detail": f"Image not found: {image}. Error: {str(e)}",
            "status": 404,
        }

    environment = {}
    if is_snapshot_build(version):
        environment.update(
            {
                "TARGET": full_target,
                "VERSION_PATH": get_branch(version)
                .get("path", "")
                .replace("{version}", version),
            }
        )

    container = podman.containers.create(
        image,
        command=["sleep", "60"],
        cap_drop=["all"],
        no_new_privileges=True,
        privileged=False,
        networks={"pasta": {}},
        auto_remove=True,
        environment=environment,
    )
    container.start()

    try:
        if is_snapshot_build(version):
            returncode, stdout, stderr = run_cmd(container, ["sh", "setup.sh"])
            if returncode:
                container.kill()
                response.status_code = 500
                return {"detail": "Could not set up ImageBuilder", "status": 500}

        returncode, stdout, stderr = run_cmd(container, ["make", "info"])

        if returncode:
            container.kill()
            response.status_code = 500
            return {
                "detail": f"Failed to get ImageBuilder info: {stderr}",
                "status": 500,
            }

        from asu.package_selection import get_profile_packages

        profile_packages = get_profile_packages(stdout, profile)

        return {"packages": sorted(profile_packages)}
    finally:
        container.kill()
