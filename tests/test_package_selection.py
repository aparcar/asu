"""Tests for package selection module."""

from asu.build_request import BuildRequest
from asu.package_selection import (
    get_default_packages,
    get_profile_packages,
    calculate_package_selection,
    validate_package_manifest,
)


def test_get_default_packages():
    """Test extraction of default packages from ImageBuilder output."""
    output = """
Some other content
Default Packages: base-files busybox dnsmasq dropbear firewall
More content
"""
    result = get_default_packages(output)
    assert result == {"base-files", "busybox", "dnsmasq", "dropbear", "firewall"}


def test_get_default_packages_empty():
    """Test get_default_packages with no match."""
    output = "No default packages line here"
    result = get_default_packages(output)
    assert result == set()


def test_get_profile_packages():
    """Test extraction of profile packages from ImageBuilder output."""
    output = """
Some content
testprofile:
    Target: testtarget/testsubtarget
    Packages: kmod-ath9k wpad-basic
More content
"""
    result = get_profile_packages(output, "testprofile")
    assert result == {"kmod-ath9k", "wpad-basic"}


def test_get_profile_packages_empty():
    """Test get_profile_packages with no match."""
    output = "No profile packages here"
    result = get_profile_packages(output, "testprofile")
    assert result == set()


def test_calculate_package_selection_no_diff():
    """Test package selection without diff_packages."""
    build_request = BuildRequest(
        version="1.2.3",
        target="testtarget/testsubtarget",
        profile="testprofile",
        packages=["vim", "tmux"],
        diff_packages=False,
    )
    default_packages = {"base-files", "busybox"}
    profile_packages = {"kmod-test"}

    result = calculate_package_selection(
        build_request, default_packages, profile_packages
    )

    # Without diff_packages, should just return requested packages
    assert result == ["vim", "tmux"]


def test_calculate_package_selection_with_diff():
    """Test package selection with diff_packages enabled."""
    build_request = BuildRequest(
        version="1.2.3",
        target="testtarget/testsubtarget",
        profile="testprofile",
        packages=["vim", "tmux"],
        diff_packages=True,
    )
    default_packages = {"base-files", "busybox"}
    profile_packages = {"kmod-test"}

    result = calculate_package_selection(
        build_request, default_packages, profile_packages
    )

    # With diff_packages, should remove default/profile packages not in request
    # and add requested packages
    assert "-base-files" in result
    assert "-busybox" in result
    assert "-kmod-test" in result
    assert "vim" in result
    assert "tmux" in result


def test_calculate_package_selection_preserves_order():
    """Test that package selection preserves user-specified order."""
    build_request = BuildRequest(
        version="1.2.3",
        target="testtarget/testsubtarget",
        profile="testprofile",
        packages=["zzz", "aaa", "mmm"],  # Intentionally out of alphabetical order
        diff_packages=False,
    )
    default_packages = set()
    profile_packages = set()

    result = calculate_package_selection(
        build_request, default_packages, profile_packages
    )

    # Order should be preserved
    assert result == ["zzz", "aaa", "mmm"]


def test_validate_package_manifest_valid():
    """Test manifest validation with matching versions."""
    manifest = {
        "vim": "8.2.1",
        "tmux": "3.1",
    }
    requested_versions = {
        "vim": "8.2.1",
        "tmux": "3.1",
    }

    result = validate_package_manifest(manifest, requested_versions)
    assert result is None


def test_validate_package_manifest_missing_package():
    """Test manifest validation with missing package."""
    manifest = {
        "vim": "8.2.1",
    }
    requested_versions = {
        "vim": "8.2.1",
        "tmux": "3.1",
    }

    result = validate_package_manifest(manifest, requested_versions)
    assert result is not None
    assert "tmux not in manifest" in result


def test_validate_package_manifest_version_mismatch():
    """Test manifest validation with version mismatch."""
    manifest = {
        "vim": "8.2.1",
        "tmux": "3.0",
    }
    requested_versions = {
        "vim": "8.2.1",
        "tmux": "3.1",
    }

    result = validate_package_manifest(manifest, requested_versions)
    assert result is not None
    assert "version not as requested" in result
    assert "tmux" in result


def test_validate_package_manifest_empty():
    """Test manifest validation with empty request."""
    manifest = {
        "vim": "8.2.1",
    }
    requested_versions = {}

    result = validate_package_manifest(manifest, requested_versions)
    assert result is None
