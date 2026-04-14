import logging
import mimetypes
from pathlib import Path
from typing import Protocol

import boto3

from asu.config import settings

log = logging.getLogger("rq.worker")


class Store(Protocol):
    def upload_file(self, local_path: Path, key: str) -> None: ...
    def upload_dir(self, local_dir: Path, prefix: str) -> None: ...
    def get_url(self, key: str) -> str: ...
    def exists(self, key: str) -> bool: ...


class LocalStore:
    def __init__(self):
        self.base = settings.public_path / "store"
        self.base.mkdir(parents=True, exist_ok=True)

    def upload_file(self, local_path: Path, key: str) -> None:
        dest = self.base / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        if local_path.resolve() != dest.resolve():
            import shutil

            shutil.copy2(local_path, dest)

    def upload_dir(self, local_dir: Path, prefix: str) -> None:
        for path in local_dir.rglob("*"):
            if path.is_file():
                key = f"{prefix}/{path.relative_to(local_dir)}"
                self.upload_file(path, key)

    def get_url(self, key: str) -> str:
        return f"/store/{key}"

    def exists(self, key: str) -> bool:
        return (self.base / key).is_file()

    def get_local_path(self, key: str) -> Path:
        return self.base / key


class S3Store:
    def __init__(self):
        kwargs = {"service_name": "s3"}
        if settings.s3_endpoint:
            kwargs["endpoint_url"] = settings.s3_endpoint
        if settings.s3_access_key:
            kwargs["aws_access_key_id"] = settings.s3_access_key
            kwargs["aws_secret_access_key"] = settings.s3_secret_key
        if settings.s3_region:
            kwargs["region_name"] = settings.s3_region

        self._client = boto3.client(**kwargs)
        self._bucket = settings.s3_bucket

    def upload_file(self, local_path: Path, key: str) -> None:
        content_type = (
            mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"
        )
        self._client.upload_file(
            str(local_path),
            self._bucket,
            f"store/{key}",
            ExtraArgs={"ContentType": content_type},
        )
        log.debug(f"Uploaded {local_path} to s3://{self._bucket}/store/{key}")

    def upload_dir(self, local_dir: Path, prefix: str) -> None:
        for path in local_dir.rglob("*"):
            if path.is_file():
                key = f"{prefix}/{path.relative_to(local_dir)}"
                self.upload_file(path, key)

    def get_url(self, key: str) -> str:
        if settings.s3_public_url:
            return f"{settings.s3_public_url.rstrip('/')}/store/{key}"
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": f"store/{key}"},
            ExpiresIn=3600,
        )

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=f"store/{key}")
            return True
        except self._client.exceptions.ClientError:
            return False


def get_store() -> Store:
    if settings.store_backend == "s3":
        return S3Store()
    return LocalStore()
