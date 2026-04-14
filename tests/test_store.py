import tempfile
from pathlib import Path

from asu.config import settings
from asu.store import LocalStore


def test_store_content_type_img(client):
    (settings.public_path / "store").mkdir(parents=True, exist_ok=True)
    (settings.public_path / "store" / "test_store_content_type.img").touch()

    response = client.head("/store/test_store_content_type.img")

    assert response.status_code == 200

    headers = response.headers
    assert headers["Content-Type"] == "application/octet-stream"


def test_store_content_type_imggz(client):
    (settings.public_path / "store").mkdir(parents=True, exist_ok=True)
    (settings.public_path / "store" / "test_store_content_type.img.gz").touch()

    response = client.head("/store/test_store_content_type.img.gz")

    assert response.status_code == 200

    headers = response.headers
    assert headers["Content-Type"] == "application/octet-stream"


def test_store_file_missing(client):
    response = client.head("/store/test_store_file_missing.bin")

    assert response.status_code == 404

    headers = response.headers
    assert headers["Content-Type"] != "application/octet-stream"


def test_local_store_upload_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.public_path = Path(tmpdir)
        store = LocalStore()

        src = Path(tmpdir) / "image.bin"
        src.write_bytes(b"firmware data")

        store.upload_file(src, "abc123/image.bin")

        dest = Path(tmpdir) / "store" / "abc123" / "image.bin"
        assert dest.is_file()
        assert dest.read_bytes() == b"firmware data"


def test_local_store_upload_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.public_path = Path(tmpdir)
        store = LocalStore()

        build_dir = Path(tmpdir) / "build"
        build_dir.mkdir()
        (build_dir / "image.bin").write_bytes(b"fw1")
        (build_dir / "profiles.json").write_text("{}")

        store.upload_dir(build_dir, "abc123")

        store_dir = Path(tmpdir) / "store" / "abc123"
        assert (store_dir / "image.bin").read_bytes() == b"fw1"
        assert (store_dir / "profiles.json").read_text() == "{}"


def test_local_store_exists():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.public_path = Path(tmpdir)
        store = LocalStore()

        assert not store.exists("abc123/image.bin")

        (Path(tmpdir) / "store" / "abc123").mkdir(parents=True)
        (Path(tmpdir) / "store" / "abc123" / "image.bin").touch()

        assert store.exists("abc123/image.bin")


def test_local_store_get_url():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.public_path = Path(tmpdir)
        store = LocalStore()

        assert store.get_url("abc123/image.bin") == "/store/abc123/image.bin"
