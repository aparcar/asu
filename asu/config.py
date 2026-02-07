from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    public_path: Path = Path.cwd() / "public"
    redis_url: str = "redis://localhost:6379"
    upstream_url: str = "https://downloads.openwrt.org"
    allow_defaults: bool = False
    async_queue: bool = True
    openwrt_config_file: Path = Path("asu.yaml")
    max_custom_rootfs_size_mb: int = 1024
    max_defaults_length: int = 20480
    repository_allow_list: list = []
    base_container: str = "ghcr.io/openwrt/imagebuilder"
    container_socket_path: str = ""
    container_identity: str = ""
    server_stats: str = ""
    log_level: str = "INFO"
    squid_cache: bool = False
    build_ttl: str = "3h"
    build_defaults_ttl: str = "30m"
    build_failure_ttl: str = "10m"
    max_pending_jobs: int = 200
    job_timeout: str = "10m"


settings = Settings()
