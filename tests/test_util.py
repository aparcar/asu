import os
import tempfile
from pathlib import Path

from podman import PodmanClient

from asu.build_request import BuildRequest
from asu.util import httpx  # For monkeypatching.
from asu.util import (
    check_manifest,
    diff_packages,
    fingerprint_pubkey_usign,
    get_container_version_tag,
    get_file_hash,
    get_packages_hash,
    get_podman,
    get_request_hash,
    get_str_hash,
    parse_feeds_conf,
    parse_manifest,
    parse_packages_file,
    parse_kernel_version,
    is_post_kmod_split_build,
    run_cmd,
    verify_usign,
)


def test_get_str_hash():
    assert (
        get_str_hash("test")
        == "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
    )


def test_get_file_hash():
    file_fd, file_path = tempfile.mkstemp()
    os.write(file_fd, b"test")

    assert get_file_hash(file_path).startswith(
        "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
    )

    os.close(file_fd)
    os.unlink(file_path)


def test_get_packages_hash():
    assert (
        get_packages_hash(["test1", "test2"])
        == "57aab5949a36e66b535a8cb13e39e9e093181c9000c016990d7be9eb86a9b9e8"
    )


def test_get_request_hash():
    request = BuildRequest(
        **{
            "distro": "test",
            "version": "test",
            "target": "testtarget/testsubtarget",
            "profile": "test",
            "packages": ["test"],
        }
    )

    assert (
        get_request_hash(request)
        == "99ff721439cd696f7da259541a07d7bfc7eb6c45a844db532e0384b464e23f46"
    )


def test_diff_packages():
    assert diff_packages(["test1"], {"test1", "test2"}) == ["-test2", "test1"]
    assert diff_packages(["test1"], {"test1"}) == ["test1"]
    assert diff_packages(["test1"], {"test2", "test3"}) == ["-test2", "-test3", "test1"]
    assert diff_packages(["test1"], {"test2", "-test3"}) == [
        "-test2",
        "-test3",
        "test1",
    ]
    assert diff_packages(["z", "x"], {"x", "y", "z"}) == ["-y", "z", "x"]
    assert diff_packages(["x", "z"], {"x", "y", "z"}) == ["-y", "x", "z"]
    assert diff_packages(["z", "y"], {"x", "y", "z"}) == ["-x", "z", "y"]
    assert diff_packages(["y", "z"], {"x", "y", "z"}) == ["-x", "y", "z"]


def test_fingerprint_pubkey_usign():
    pub_key = "RWSrHfFmlHslUcLbXFIRp+eEikWF9z1N77IJiX5Bt/nJd1a/x+L+SU89"
    assert fingerprint_pubkey_usign(pub_key) == "ab1df166947b2551"


def test_verify_usign():
    sig = b"\nRWSrHfFmlHslUQ9dCB1AJr/PoIIbBJJKtofZ5frLOuG03SlwAwgU1tYOaJs2eVGdo1C8S9LNcMBLPIfDDCWSdrLK3WJ6JV6HNQM="
    msg_fd, msg_path = tempfile.mkstemp()
    sig_fd, sig_path = tempfile.mkstemp()
    os.write(msg_fd, b"test\n")
    os.write(sig_fd, sig)

    pub_key = "RWSrHfFmlHslUcLbXFIRp+eEikWF9z1N77IJiX5Bt/nJd1a/x+L+SU89"
    pub_key_bad = "rWSrHfFmlHslUcLbXFIRp+eEikWF9z1N77IJiX5Bt/nJd1a/x+L+SXXX"

    assert verify_usign(Path(sig_path), Path(msg_path), pub_key)
    assert not verify_usign(Path(sig_path), Path(msg_path), pub_key_bad)

    os.close(msg_fd)
    os.close(sig_fd)
    os.unlink(msg_path)
    os.unlink(sig_path)


def test_get_version_container_tag():
    assert get_container_version_tag("1.0.0") == "v1.0.0"
    assert get_container_version_tag("SNAPSHOT") == "master"
    assert get_container_version_tag("1.0.0-SNAPSHOT") == "openwrt-1.0.0"
    assert get_container_version_tag("23.05.0-rc3") == "v23.05.0-rc3"
    assert get_container_version_tag("SNAPP-SNAPSHOT") == "openwrt-SNAPP"


def test_get_packages_versions(monkeypatch):
    class Response:
        status_code = 200
        text = (
            "Package: libusb-1.0-0\n"
            "ABIVersion: -0\n"
            "Version: 1.2.3\n"
            "Architecture: x86_64\n"
            "\n"
            "Package: libpython-3.3-3\n"
            "ABIVersion: -3\n"
            "Version: 1.2.3\n"
            "\n"
            "Package: bort\n"
            "Version: 9.9.9\n"
            "\n"
            "\n"  # Add two more to fake malformed input.
            "\n"
        )

    monkeypatch.setattr(httpx, "get", lambda url: Response())

    index = parse_packages_file("httpx://fake_url")
    packages = index["packages"]

    assert index["architecture"] == "x86_64"
    assert len(packages) == 3
    assert packages["libusb-1.0"] == "1.2.3"
    assert packages["libpython-3.3"] == "1.2.3"
    assert packages["bort"] == "9.9.9"

    Response.status_code = 404
    index = parse_packages_file("abc://fake")
    assert index == {}


def test_get_kernel_version(monkeypatch):
    class Response:
        status_code = 200

        json_data = {
            "linux_kernel": {
                "release": "1",
                "vermagic": "ed1b0ea64b60bcea5dd4112f33d0dcbe",
                "version": "6.6.63",
            },
        }

        def json(self):
            return Response.json_data

    monkeypatch.setattr(httpx, "get", lambda url: Response())

    version = parse_kernel_version("httpx://fake_url")
    assert version == "6.6.63-1-ed1b0ea64b60bcea5dd4112f33d0dcbe"

    Response.json_data = {}
    version = parse_kernel_version("httpx://fake_url")
    assert version == ""


def test_check_kmod_split():
    cases = {
        "releases/22.07.3/targets/x86/64": False,
        "releases/23.05.0-rc3/targets/x86/64": False,
        "releases/23.05.2/targets/x86/64": False,
        "releases/23.05.5/targets/x86/64": False,
        "releases/23.05.6/targets/x86/64": True,
        "releases/23.05-SNAPSHOT/targets/x86/64": True,
        "releases/24.10.0-rc1/targets/x86/64": True,
        "releases/24.10.2/targets/x86/64": True,
        "releases/24.10-SNAPSHOT/targets/x86/64": True,
        "snapshots/targets/x86/64": True,
    }

    for path, expected in cases.items():
        result: bool = is_post_kmod_split_build(path)
        assert result == expected


def test_get_feeds(monkeypatch):
    class Response:
        status_code = 200
        text = (
            "src-git packages https://git.openwrt.org/feed/packages.git^b1635b8\n"
            "src-git luci https://git.openwrt.org/project/luci.git^63d8b79\n"
        )

    monkeypatch.setattr(httpx, "get", lambda url: Response())

    feeds = parse_feeds_conf("httpx://fake_url")
    assert len(feeds) == 2
    assert feeds[0] == "packages"
    assert feeds[1] == "luci"

    Response.status_code = 404
    feeds = parse_feeds_conf("httpx://fake_url")
    assert feeds == []


def test_check_manifest():
    assert check_manifest({"test": "1.0"}, {"test": "1.0"}) is None
    assert (
        check_manifest({"test": "1.0"}, {"test": "2.0"})
        == "Impossible package selection: test version not as requested: 2.0 vs. 1.0"
    )
    assert (
        check_manifest({"test": "1.0"}, {"test2": "1.0"})
        == "Impossible package selection: test2 not in manifest"
    )


def test_get_podman():
    podman = get_podman()
    assert isinstance(podman, PodmanClient)


def test_run_cmd():
    podman = get_podman()
    podman.images.pull("ghcr.io/openwrt/imagebuilder:testtarget-testsubtarget-v1.2.3")

    container = podman.containers.create(
        "ghcr.io/openwrt/imagebuilder:testtarget-testsubtarget-v1.2.3",
        command=["sleep", "1000"],
        detach=True,
    )
    container.start()

    returncode, stdout, stderr = run_cmd(
        container,
        ["make", "info"],
    )

    assert returncode == 0
    assert "testtarget/testsubtarget" in stdout


def test_parse_manifest_opkg():
    manifest = parse_manifest(
        "test - 1.0\n" "test2 - 2.0\n" "test3 - 3.0\n" "test4 - 3.0\n"
    )

    assert manifest == {
        "test": "1.0",
        "test2": "2.0",
        "test3": "3.0",
        "test4": "3.0",
    }


def test_parse_manifest_apk():
    manifest = parse_manifest("test 1.0\n" "test2 2.0\n" "test3 3.0\n" "test4 3.0\n")

    assert manifest == {
        "test": "1.0",
        "test2": "2.0",
        "test3": "3.0",
        "test4": "3.0",
    }
