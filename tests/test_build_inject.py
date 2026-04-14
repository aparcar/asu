"""Test build file injection logic (keys, repos, defaults).

Tests verify that _make_tar produces correct archives and that
inject_files constructs the right file trees for the container.
"""

import base64
import tarfile
from io import BytesIO
from unittest.mock import MagicMock, patch

from asu.build import _make_tar, inject_files
from asu.build_request import BuildRequest


def _extract_tar(data: bytes) -> dict[str, str]:
    """Helper: extract tar bytes into {name: content} dict."""
    result = {}
    with tarfile.open(fileobj=BytesIO(data)) as tar:
        for member in tar.getmembers():
            if member.isfile():
                result[member.name] = tar.extractfile(member).read().decode("utf-8")
    return result


def test_make_tar_single_file():
    data = _make_tar({"hello.txt": "world"})
    files = _extract_tar(data)
    assert files == {"hello.txt": "world"}


def test_make_tar_multiple_files():
    data = _make_tar(
        {
            "a.txt": "aaa",
            "sub/b.txt": "bbb",
        }
    )
    files = _extract_tar(data)
    assert files["a.txt"] == "aaa"
    assert files["sub/b.txt"] == "bbb"


def test_make_tar_binary_content():
    data = _make_tar({"bin.dat": b"\x00\x01\x02"})
    with tarfile.open(fileobj=BytesIO(data)) as tar:
        content = tar.extractfile("bin.dat").read()
    assert content == b"\x00\x01\x02"


def test_make_tar_empty():
    data = _make_tar({})
    with tarfile.open(fileobj=BytesIO(data)) as tar:
        assert tar.getmembers() == []


def test_inject_files_no_extras():
    """No keys, repos, or defaults — nothing should be injected."""
    container = MagicMock()
    request = BuildRequest(
        version="1.2.3",
        target="testtarget/testsubtarget",
        profile="testprofile",
    )
    inject_files(container, request)
    container.put_archive.assert_not_called()


@patch("asu.build._detect_apk_mode", return_value=False)
def test_inject_files_with_defaults(mock_detect):
    container = MagicMock()
    request = BuildRequest(
        version="1.2.3",
        target="testtarget/testsubtarget",
        profile="testprofile",
        defaults="echo hello",
    )
    inject_files(container, request)
    container.put_archive.assert_called_once()

    call_args = container.put_archive.call_args
    assert call_args[0][0] == "/builder/"
    files = _extract_tar(call_args[0][1])
    assert "asu-files/etc/uci-defaults/99-asu-defaults" in files
    assert files["asu-files/etc/uci-defaults/99-asu-defaults"] == "echo hello"


@patch("asu.build._detect_apk_mode", return_value=False)
def test_inject_files_with_repositories(mock_detect):
    container = MagicMock()
    request = BuildRequest(
        version="1.2.3",
        target="testtarget/testsubtarget",
        profile="testprofile",
        repositories={},
    )
    inject_files(container, request)
    container.put_archive.assert_not_called()


def test_inject_files_with_usign_keys():
    """usign keys go to /builder/keys/."""
    container = MagicMock()
    key_data = base64.b64encode(b"\x00" * 42).decode()
    request = BuildRequest(
        version="1.2.3",
        target="testtarget/testsubtarget",
        profile="testprofile",
        repository_keys=[key_data],
    )
    inject_files(container, request)
    container.put_archive.assert_called_once()

    call_args = container.put_archive.call_args
    assert call_args[0][0] == "/builder/"
    files = _extract_tar(call_args[0][1])
    key_files = [f for f in files if f.startswith("keys/")]
    assert len(key_files) == 1
    assert key_data in files[key_files[0]]


def test_inject_files_with_pem_keys():
    """PEM keys also go to /builder/keys/."""
    container = MagicMock()
    pem_key = "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZI...\n-----END PUBLIC KEY-----\n"
    request = BuildRequest(
        version="25.12.2",
        target="testtarget/testsubtarget",
        profile="testprofile",
        repository_keys=[pem_key],
    )
    inject_files(container, request)
    container.put_archive.assert_called_once()

    call_args = container.put_archive.call_args
    assert call_args[0][0] == "/builder/"
    files = _extract_tar(call_args[0][1])
    pem_files = [f for f in files if f.endswith(".pem")]
    assert len(pem_files) == 1
    assert pem_key in files[pem_files[0]]


def test_inject_files_mixed_keys():
    """Both PEM and usign keys in one request go to /builder/keys/."""
    container = MagicMock()
    pem_key = "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZI...\n-----END PUBLIC KEY-----\n"
    usign_key = base64.b64encode(b"\x00" * 42).decode()
    request = BuildRequest(
        version="25.12.2",
        target="testtarget/testsubtarget",
        profile="testprofile",
        repository_keys=[pem_key, usign_key],
    )
    inject_files(container, request)
    container.put_archive.assert_called_once()

    call_args = container.put_archive.call_args
    assert call_args[0][0] == "/builder/"
    files = _extract_tar(call_args[0][1])
    assert len(files) == 2


@patch("asu.build._detect_apk_mode", return_value=False)
def test_inject_files_defaults_and_keys(mock_detect):
    """Multiple inject types should result in multiple put_archive calls."""
    container = MagicMock()
    key_data = base64.b64encode(b"\x00" * 42).decode()
    request = BuildRequest(
        version="1.2.3",
        target="testtarget/testsubtarget",
        profile="testprofile",
        defaults="echo test",
        repository_keys=[key_data],
    )
    inject_files(container, request)
    assert container.put_archive.call_count == 2
