import logging
from typing import Union

from fastapi import APIRouter, Header, Request
from fastapi.responses import RedirectResponse, Response

from asu.build import build
from asu.build_request import BuildRequest
from asu.config import settings
from asu.util import (
    add_timestamp,
    add_build_event,
    client_get,
    get_branch,
    get_queue,
    get_request_hash,
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


def build_job_response(job) -> tuple[dict, int, dict]:
    """Build API response from job state.

    Args:
        job: BuildJob instance

    Returns:
        Tuple of (response_dict, status_code, headers_dict)
    """
    state = job.get_state(refresh=True)

    if not state:
        return {"status": 404, "detail": "Job not found"}, 404, {}

    # Base response with metadata
    response = {
        "request_hash": state["id"],
        "enqueued_at": state["enqueued_at"],
        **state["meta"],  # Include all metadata
    }

    # Status-specific handling
    status_code = 200
    imagebuilder_status = "done"
    queue_position = 0

    if state["status"] == "queued":
        status_code = 202
        response["status"] = 202
        response["detail"] = "queued"
        response["queue_position"] = state.get("queue_position", 0)
        queue_position = state.get("queue_position", 0)
        imagebuilder_status = "queued"

    elif state["status"] == "started":
        status_code = 202
        response["status"] = 202
        response["detail"] = "started"
        imagebuilder_status = state["meta"].get("imagebuilder_status", "init")

    elif state["status"] == "finished":
        status_code = 200
        response["status"] = 200
        if state["result"]:
            response.update(state["result"])
        imagebuilder_status = "done"

    elif state["status"] == "failed":
        status_code = 500
        response["status"] = 500
        error_message = state.get("exc_string", "Unknown error")
        if "stderr" in state["meta"]:
            error_message = state["meta"]["stderr"] + "\n" + error_message
        detail = state["meta"].get("detail", "failed")
        if detail == "init":
            detail = "failed"
        response.update(status=500, detail=detail, stderr=error_message)
        imagebuilder_status = "failed"

    headers = {
        "X-Imagebuilder-Status": imagebuilder_status,
        "X-Queue-Position": str(queue_position),
    }

    logging.debug(response)
    return response, status_code, headers


@router.head("/build/{request_hash}")
@router.get("/build/{request_hash}")
def api_v1_build_get(request: Request, request_hash: str, response: Response) -> dict:
    job = get_queue().fetch_job(request_hash)
    if not job:
        response.status_code = 404
        return {
            "status": 404,
            "title": "Not Found",
            "detail": "could not find provided request hash",
        }

    content, status, headers = build_job_response(job)
    response.headers.update(headers)
    response.status_code = status

    return content


@router.post("/build")
def api_v1_build_post(
    build_request: BuildRequest,
    response: Response,
    request: Request,
    user_agent: str = Header(None),
):
    # Sanitize the profile in case the client did not (bug in older LuCI app).
    build_request.profile = build_request.profile.replace(",", "_")

    add_build_event("requests")

    request_hash: str = get_request_hash(build_request)
    job = get_queue().fetch_job(request_hash)
    status: int = 200
    result_ttl: str = settings.build_ttl
    if build_request.defaults:
        result_ttl = settings.build_defaults_ttl
    failure_ttl: str = settings.build_failure_ttl

    if build_request.client:
        client = build_request.client
    elif user_agent.startswith("auc"):
        client = user_agent.replace(" (", "/").replace(")", "")
    else:
        client = "unknown/0"

    add_timestamp(
        f"stats:clients:{client}",
        {"stats": "clients", "client": client},
    )

    if job is None:
        add_build_event("cache-misses")

        content, status = validate_request(request.app, build_request)
        if content:
            response.status_code = status
            return content

        job_queue_length = len(get_queue())
        if job_queue_length > settings.max_pending_jobs:
            response.status_code = 529
            return {
                "status": 529,  # "Site is overloaded"
                "title": "Server overloaded",
                "detail": f"server overload, queue contains too many build requests: {job_queue_length}",
            }

        job = get_queue().enqueue(
            build,
            build_request,
            job_id=request_hash,
            result_ttl=result_ttl,
            failure_ttl=failure_ttl,
            job_timeout=settings.job_timeout,
        )
    else:
        if job.status == "finished":
            add_build_event("cache-hits")

    content, status, headers = build_job_response(job)
    response.headers.update(headers)
    response.status_code = status

    return content


@router.get("/stats")
def api_v1_builder_stats():
    """Return status of builders

    Returns:
        queue_length: Number of jobs currently in build queue
    """
    return {
        "queue_length": len(get_queue()),
    }
