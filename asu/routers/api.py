import logging
from typing import Union

from fastapi import APIRouter, Header, Request
from fastapi.responses import RedirectResponse, Response
from rq.job import Job

from asu.build_request import BuildRequest
from asu.config import settings
from asu.services.prepare_service import get_prepare_service
from asu.services.build_service import get_build_service
from asu.util import (
    client_get,
    get_branch,
    get_queue,
    reload_profiles,
    reload_targets,
    reload_versions,
)

router = APIRouter()


def get_distros() -> list:
    """Return available distributions

    Returns:
        list: Available distributions
    """
    return ["openwrt"]


@router.get("/revision/{version}/{target}/{subtarget}")
def api_v1_revision(
    version: str, target: str, subtarget: str, response: Response, request: Request
):
    branch_data = get_branch(version)
    version_path = branch_data["path"].format(version=version)
    req = client_get(
        settings.upstream_url
        + f"/{version_path}/targets/{target}/{subtarget}/profiles.json"
    )

    if req.status_code != 200:
        response.status_code = req.status_code
        return {
            "detail": f"Failed to fetch revision for {version}/{target}/{subtarget}",
            "status": req.status_code,
        }

    return {"revision": req.json()["version_code"]}


@router.get("/latest")
def api_latest():
    return RedirectResponse("/json/v1/latest.json", status_code=301)


@router.get("/overview")
def api_v1_overview():
    return RedirectResponse("/json/v1/overview.json", status_code=301)


def validation_failure(detail: str) -> tuple[dict[str, Union[str, int]], int]:
    logging.info(f"Validation failure {detail = }")
    return {"detail": detail, "status": 400}, 400


def validate_request(
    app,
    build_request: BuildRequest,
) -> tuple[dict[str, Union[str, int]], int]:
    """Validate an image request and return found errors with status code

    Instead of building every request it is first validated. This checks for
    existence of requested profile, distro, version and package.

    Args:
        req (dict): The image request

    Returns:
        (dict, int): Status message and code, empty if no error appears

    """

    if build_request.defaults and not settings.allow_defaults:
        return validation_failure("Handling `defaults` not enabled on server")

    if build_request.distro not in get_distros():
        return validation_failure(f"Unsupported distro: {build_request.distro}")

    branch = get_branch(build_request.version)["name"]

    if branch not in settings.branches:
        return validation_failure(f"Unsupported branch: {build_request.version}")

    if build_request.version not in app.versions:
        reload_versions(app)
        if build_request.version not in app.versions:
            return validation_failure(f"Unsupported version: {build_request.version}")

    build_request.packages: list[str] = [
        x.removeprefix("+")
        for x in (build_request.packages_versions.keys() or build_request.packages)
    ]

    if build_request.target not in app.targets[build_request.version]:
        reload_targets(app, build_request.version)
        if build_request.target not in app.targets[build_request.version]:
            return validation_failure(
                f"Unsupported target: {build_request.target}. The requested "
                "target was either dropped, is still being built or is not "
                "supported by the selected version. Please check the forums or "
                "try again later."
            )

    def valid_profile(profile: str, build_request: BuildRequest) -> bool:
        profiles = app.profiles[build_request.version][build_request.target]
        if profile in profiles:
            return True
        if len(profiles) == 1 and "generic" in profiles:
            # Handles the x86, armsr and other generic variants.
            build_request.profile = "generic"
            return True
        return False

    if not valid_profile(build_request.profile, build_request):
        reload_profiles(app, build_request.version, build_request.target)
        if not valid_profile(build_request.profile, build_request):
            return validation_failure(
                f"Unsupported profile: {build_request.profile}. The requested "
                "profile was either dropped or never existed. Please check the "
                "forums for more information."
            )

    build_request.profile = app.profiles[build_request.version][build_request.target][
        build_request.profile
    ]
    return ({}, None)


def return_job_v1(job: Job) -> tuple[dict, int, dict]:
    response: dict = job.get_meta()
    imagebuilder_status: str = "done"
    queue_position: int = 0

    if job.meta:
        response.update(job.meta)

    if job.is_failed:
        error_message: str = job.latest_result().exc_string
        if "stderr" in response:
            error_message = response["stderr"] + "\n" + error_message
        detail: str = response.get("detail", "failed")
        if detail == "init":  # Happens when container startup fails.
            detail = "failed"
        response.update(status=500, detail=detail, stderr=error_message)
        imagebuilder_status = "failed"

    elif job.is_queued:
        queue_position = job.get_position() or 0
        response.update(status=202, detail="queued", queue_position=queue_position)
        imagebuilder_status = "queued"

    elif job.is_started:
        response.update(status=202, detail="started")
        imagebuilder_status = response.get("imagebuilder_status", "init")

    elif job.is_finished:
        response.update(status=200, **job.return_value())
        imagebuilder_status = "done"

    headers = {
        "X-Imagebuilder-Status": imagebuilder_status,
        "X-Queue-Position": str(queue_position),
    }

    response.update(enqueued_at=job.enqueued_at, request_hash=job.id)

    logging.debug(response)
    return response, response["status"], headers


@router.post("/build/prepare")
def api_v1_build_prepare(
    build_request: BuildRequest,
    response: Response,
    request: Request,
):
    """
    Prepare a build request without executing it.

    This endpoint runs in the lightweight prepare service which can be
    deployed independently from the build service.

    This endpoint:
    1. Validates the request
    2. Applies package changes based on version/target/profile
    3. Returns the final package list and changes for user approval
    4. Does NOT queue a build job

    The prepared request can be sent to /build with skip_package_resolution=true
    to build exactly what was prepared.
    """
    # Use the independent prepare service
    prepare_service = get_prepare_service(request.app)
    result = prepare_service.prepare(build_request)

    # Handle error responses
    if "status" in result and result["status"] != "prepared":
        response.status_code = result["status"]

    # Note: Cache checking removed from prepare service as it requires Redis.
    # Cache checking is now only in the build service.
    # Clients should call build endpoint to check cache availability.

    return result


@router.head("/build/{request_hash}")
@router.get("/build/{request_hash}")
def api_v1_build_get(request: Request, request_hash: str, response: Response) -> dict:
    job: Job = get_queue().fetch_job(request_hash)
    if not job:
        response.status_code = 404
        return {
            "status": 404,
            "title": "Not Found",
            "detail": "could not find provided request hash",
        }

    content, status, headers = return_job_v1(job)
    response.headers.update(headers)
    response.status_code = status

    return content


@router.post("/build")
def api_v1_build_post(
    build_request: BuildRequest,
    response: Response,
    request: Request,
    user_agent: str = Header(None),
    skip_package_resolution: bool = False,
):
    """
    Build a firmware image.

    This endpoint runs in the heavy build service which requires Redis,
    RQ, Podman, and ImageBuilder. It can be deployed independently from
    the prepare service.

    Args:
        build_request: The build request parameters
        skip_package_resolution: If True, skip package resolution (used when
            building from a prepared request). Default: False

    If skip_package_resolution=True, assumes packages are already resolved
    and skips package changes/migrations. This should be used when calling
    /build after /build/prepare.
    """
    # Determine client identifier
    if build_request.client:
        client = build_request.client
    elif user_agent and user_agent.startswith("auc"):
        client = user_agent.replace(" (", "/").replace(")", "")
    else:
        client = "unknown/0"

    # Use the independent build service
    build_service = get_build_service(request.app)
    result = build_service.build(
        build_request,
        skip_package_resolution=skip_package_resolution,
        client=client,
    )

    # Extract headers if present
    headers = result.pop("headers", {})
    response.headers.update(headers)

    # Set status code
    response.status_code = result.get("status", 200)

    return result


@router.get("/stats")
def api_v1_builder_stats():
    """Return status of builders

    Returns:
        queue_length: Number of jobs currently in build queue
    """
    return {
        "queue_length": len(get_queue()),
    }
