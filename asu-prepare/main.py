"""
ASU Prepare Service - Standalone FastAPI Application

This is a completely independent microservice that runs separately from
the build service. It handles only package resolution and validation.

No dependencies on:
- Redis/RQ
- Podman
- Build infrastructure
- ASU build service code

Communication:
- Accepts HTTP requests
- Returns JSON responses
- Build service calls this via HTTP
"""

import logging
from typing import Optional
from copy import deepcopy

from fastapi import FastAPI, Response, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from prepare_request import PrepareRequest
from package_resolution import PackageResolver
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("asu-prepare")

# Create FastAPI app
app = FastAPI(
    title="ASU Prepare Service",
    description="Package resolution and validation service for OpenWrt firmware builds",
    version=settings.service_version,
)

# Add CORS middleware to allow cross-origin requests from build service
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to build service URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def calculate_request_hash(prepare_request: PrepareRequest) -> str:
    """
    Calculate a reproducible hash for a build request.

    This is a simplified version that doesn't require the full util.py module.
    """
    import hashlib
    import json

    # Serialize request to consistent JSON
    data = prepare_request.model_dump()
    # Sort packages for consistency
    if "packages" in data and data["packages"]:
        data["packages"] = sorted(data["packages"])

    # Create hash
    serialized = json.dumps(data, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


@app.get("/")
async def root():
    """Root endpoint - service information"""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "running",
        "endpoints": {
            "prepare": "POST /api/v1/prepare",
            "health": "GET /health",
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers"""
    return {"status": "healthy", "service": settings.service_name}


@app.post("/api/v1/prepare")
async def prepare(prepare_request: PrepareRequest, response: Response):
    """
    Prepare a build request without executing it.

    This endpoint:
    1. Validates basic request structure (Pydantic does this)
    2. Sanitizes the profile name
    3. Applies package changes based on version/target/profile
    4. Returns the final package list and changes for user approval
    5. Does NOT queue a build job (no Redis access)
    6. Does NOT check cache (no Redis access)

    The build service will call this endpoint, then handle queueing and caching.
    """
    try:
        # Sanitize the profile
        prepare_request.profile = prepare_request.profile.replace(",", "_")

        # Create a copy to preserve the original
        request_copy = deepcopy(prepare_request)

        # Resolve packages and track changes
        resolver = PackageResolver()
        final_packages, changes = resolver.resolve(request_copy)

        # Create prepared request (with resolved packages)
        # This is what the build service will receive
        prepared_request = PrepareRequest(
            distro=prepare_request.distro,
            version=prepare_request.version,
            from_version=prepare_request.from_version,
            target=prepare_request.target,
            profile=request_copy.profile,  # Use sanitized profile
            packages=final_packages,
        )

        # Calculate hash of the prepared request
        request_hash = calculate_request_hash(prepared_request)

        log.info(
            f"Prepared request for {prepare_request.version}/{prepare_request.target}/"
            f"{prepare_request.profile} with {len(changes)} changes"
        )

        return {
            "status": "prepared",
            # Original request info
            "original_packages": prepare_request.packages,
            # Resolved packages
            "resolved_packages": final_packages,
            # What changed
            "changes": [c.to_dict() for c in changes],
            # Prepared request to send to /build
            "prepared_request": prepared_request.model_dump(),
            "request_hash": request_hash,
        }

    except Exception as e:
        log.error(f"Error preparing request: {e}", exc_info=True)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {
            "status": "error",
            "detail": f"Failed to prepare request: {str(e)}",
        }


@app.get("/api/v1/status")
async def service_status():
    """Service status endpoint"""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "operational",
        "capabilities": {
            "package_resolution": True,
            "package_migration": True,
            "request_validation": True,
            "build_execution": False,  # This service does NOT build
            "caching": False,  # This service does NOT cache
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
