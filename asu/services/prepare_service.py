"""
Prepare Service - Lightweight microservice for package resolution

This service can run independently in its own container without heavy
dependencies like Redis, RQ, or Podman. It only performs:
1. Request validation
2. Package resolution and change tracking
3. Prepared request generation

Dependencies:
- BuildRequest model
- Package resolution logic
- Validation utilities (version/target/profile data)

No dependencies on:
- Redis/RQ (no queue management)
- Podman (no container operations)
- Build infrastructure
"""

import logging
from typing import Optional
from copy import deepcopy

from asu.build_request import BuildRequest
from asu.package_resolution import PackageResolver
from asu.util import get_request_hash

log = logging.getLogger("asu.prepare")


class PrepareService:
    """
    Independent prepare service that can run in its own container.

    This service is stateless and lightweight. It only validates requests
    and resolves packages without touching the build infrastructure.
    """

    def __init__(self, app=None):
        """
        Initialize the prepare service.

        Args:
            app: Optional FastAPI app instance for validation data access.
                 If None, validation will be skipped (useful for testing).
        """
        self.app = app

    def prepare(
        self, build_request: BuildRequest
    ) -> dict:
        """
        Prepare a build request without executing it.

        This method:
        1. Validates the request (if app is provided)
        2. Applies package changes based on version/target/profile
        3. Returns the final package list and changes for user approval
        4. Does NOT queue a build job or check cache

        Args:
            build_request: The build request to prepare

        Returns:
            Dictionary with preparation results including:
            - status: "prepared"
            - original_packages: Original package list
            - resolved_packages: Final package list after changes
            - changes: List of package changes made
            - prepared_request: Ready-to-build request
            - request_hash: Hash of the prepared request
        """
        # Sanitize the profile
        build_request.profile = build_request.profile.replace(",", "_")

        # Validate if app is available (skip for standalone mode)
        if self.app:
            error = self._validate_request(build_request)
            if error:
                return error

        # Create a copy to preserve the original
        request_copy = deepcopy(build_request)

        # Resolve packages and track changes
        resolver = PackageResolver()
        final_packages, changes = resolver.resolve(request_copy)

        # Create prepared request (with resolved packages, diff_packages=False)
        prepared_request = BuildRequest(
            distro=build_request.distro,
            version=build_request.version,
            from_version=build_request.from_version,
            version_code=build_request.version_code,
            target=build_request.target,
            profile=request_copy.profile,  # Use validated profile
            packages=final_packages,
            packages_versions=build_request.packages_versions,
            diff_packages=False,  # Already resolved
            defaults=build_request.defaults,
            rootfs_size_mb=build_request.rootfs_size_mb,
            repositories=build_request.repositories,
            repository_keys=build_request.repository_keys,
            client=build_request.client,
        )

        # Calculate hash of the prepared request
        request_hash = get_request_hash(prepared_request)

        return {
            "status": "prepared",
            # Original request info
            "original_packages": build_request.packages,
            "original_diff_packages": build_request.diff_packages,
            # Resolved packages
            "resolved_packages": final_packages,
            # What changed
            "changes": [c.to_dict() for c in changes],
            # Prepared request to send to /build
            "prepared_request": prepared_request.model_dump(),
            "request_hash": request_hash,
        }

    def _validate_request(self, build_request: BuildRequest) -> Optional[dict]:
        """
        Validate a build request.

        This imports validation logic only when needed, allowing the
        prepare service to run without the full build infrastructure.

        Args:
            build_request: Request to validate

        Returns:
            Error dict if validation fails, None if valid
        """
        # Import only when needed to avoid circular dependencies
        from asu.routers.api import validate_request

        content, status = validate_request(self.app, build_request)
        if content:
            return {
                "status": status,
                "detail": content.get("detail", "Validation failed"),
            }
        return None


# Singleton instance for easy access
_prepare_service: Optional[PrepareService] = None


def get_prepare_service(app=None) -> PrepareService:
    """
    Get or create the prepare service singleton.

    Args:
        app: Optional FastAPI app instance

    Returns:
        PrepareService instance
    """
    global _prepare_service
    if _prepare_service is None or app is not None:
        _prepare_service = PrepareService(app)
    return _prepare_service
