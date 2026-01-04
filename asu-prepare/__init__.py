"""
ASU Prepare Service - Independent Microservice

This is a standalone microservice that handles package resolution and
validation for OpenWrt firmware build requests.

It does NOT:
- Build firmware (no Podman, no ImageBuilder)
- Queue jobs (no Redis, no RQ)
- Store state (completely stateless)

It DOES:
- Validate build requests
- Apply package changes/migrations
- Return resolved package lists
- Provide detailed change tracking
"""

__version__ = "1.0.0"
