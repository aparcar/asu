"""
Build Service - Heavy microservice for firmware building

This service handles the actual firmware building and requires:
- Redis/RQ for job queue management
- Podman for container operations
- ImageBuilder containers
- File storage for firmware images

This service can accept:
1. Raw build requests (applies package resolution automatically)
2. Prepared requests (skips package resolution)

Dependencies:
- Redis/RQ for asynchronous job processing
- Podman for secure containerized builds
- Build infrastructure and storage
"""

import logging
from typing import Optional

from asu.build import build as build_firmware
from asu.build_request import BuildRequest
from asu.config import settings
from asu.util import (
    add_timestamp,
    add_build_event,
    get_queue,
    get_request_hash,
)

log = logging.getLogger("asu.build")


class BuildService:
    """
    Independent build service that can run in its own container.

    This service is stateful and requires heavy infrastructure (Redis,
    Podman, ImageBuilder). It handles the actual firmware compilation.
    """

    def __init__(self, app=None):
        """
        Initialize the build service.

        Args:
            app: Optional FastAPI app instance for validation data access
        """
        self.app = app

    def build(
        self,
        build_request: BuildRequest,
        skip_package_resolution: bool = False,
        client: str = "unknown/0",
    ) -> dict:
        """
        Build a firmware image.

        This method:
        1. Validates the request (unless skip_package_resolution=True)
        2. Checks cache for existing build
        3. Queues build job if not cached
        4. Returns job status

        Args:
            build_request: The build request parameters
            skip_package_resolution: If True, skip package resolution
                (used when building from a prepared request)
            client: Client identifier for statistics

        Returns:
            Dictionary with build status and job information
        """
        # Sanitize the profile
        build_request.profile = build_request.profile.replace(",", "_")

        # Record build request
        add_build_event("requests")

        # Calculate request hash
        request_hash: str = get_request_hash(build_request)

        # Check if build already exists in queue/cache
        job = get_queue().fetch_job(request_hash)

        # Set TTL based on request type
        result_ttl: str = settings.build_ttl
        if build_request.defaults:
            result_ttl = settings.build_defaults_ttl
        failure_ttl: str = settings.build_failure_ttl

        # Track client statistics
        add_timestamp(
            f"stats:clients:{client}",
            {"stats": "clients", "client": client},
        )

        if job is None:
            # No existing build, need to create one
            add_build_event("cache-misses")

            # Validate only if not already prepared
            if not skip_package_resolution and self.app:
                error = self._validate_request(build_request)
                if error:
                    return error

            # Check queue capacity
            job_queue_length = len(get_queue())
            if job_queue_length > settings.max_pending_jobs:
                return {
                    "status": 529,  # "Site is overloaded"
                    "title": "Server overloaded",
                    "detail": f"server overload, queue contains too many build requests: {job_queue_length}",
                }

            # Enqueue the build job
            job = get_queue().enqueue(
                build_firmware,
                build_request,
                skip_package_resolution=skip_package_resolution,
                job_id=request_hash,
                result_ttl=result_ttl,
                failure_ttl=failure_ttl,
                job_timeout=settings.job_timeout,
            )
        else:
            # Build exists in cache
            if job.is_finished:
                add_build_event("cache-hits")

        # Return job status
        return self._get_job_status(job)

    def _validate_request(self, build_request: BuildRequest) -> Optional[dict]:
        """
        Validate a build request.

        Args:
            build_request: Request to validate

        Returns:
            Error dict if validation fails, None if valid
        """
        # Import only when needed
        from asu.routers.api import validate_request

        content, status = validate_request(self.app, build_request)
        if content:
            return {
                "status": status,
                "detail": content.get("detail", "Validation failed"),
            }
        return None

    def _get_job_status(self, job) -> dict:
        """
        Get the status of a build job.

        Args:
            job: RQ job instance

        Returns:
            Dictionary with job status and metadata
        """
        # Import to avoid circular dependency
        from asu.routers.api import return_job_v1

        content, status, headers = return_job_v1(job)
        return {
            **content,
            "status": status,
            "headers": headers,
        }


# Singleton instance for easy access
_build_service: Optional[BuildService] = None


def get_build_service(app=None) -> BuildService:
    """
    Get or create the build service singleton.

    Args:
        app: Optional FastAPI app instance

    Returns:
        BuildService instance
    """
    global _build_service
    if _build_service is None or app is not None:
        _build_service = BuildService(app)
    return _build_service
