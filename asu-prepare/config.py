"""
Minimal configuration for prepare service

No Redis, No Podman, No build infrastructure.
Only validation and package resolution settings.
"""

from pydantic_settings import BaseSettings


class PrepareSettings(BaseSettings):
    """Settings for the prepare service"""

    # Defaults validation
    max_defaults_length: int = 20480
    max_custom_rootfs_size_mb: int = 1024

    # Upstream for validation data
    upstream_url: str = "https://downloads.openwrt.org"

    # Service identification
    service_name: str = "asu-prepare"
    service_version: str = "1.0.0"

    # Supported branches (simplified, could be loaded dynamically)
    branches: dict[str, dict[str, str]] = {
        "SNAPSHOT": {"name": "SNAPSHOT", "path": "snapshots"},
        "24.10": {"name": "24.10", "path": "releases/{version}"},
        "23.05": {"name": "23.05", "path": "releases/{version}"},
        "22.03": {"name": "22.03", "path": "releases/{version}"},
        "21.02": {"name": "21.02", "path": "releases/{version}"},
    }


# Global settings instance
settings = PrepareSettings()
