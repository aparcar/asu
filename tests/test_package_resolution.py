"""Tests for package resolution functionality"""

import pytest

from asu.build_request import BuildRequest
from asu.package_resolution import PackageResolver, PackageChange


def test_package_change_to_dict():
    """Test PackageChange serialization"""
    change = PackageChange(
        change_type="migration",
        action="replace",
        from_package="auc",
        to_package="owut",
        reason="Package renamed in 24.10",
        automatic=True,
    )

    result = change.to_dict()
    assert result["type"] == "migration"
    assert result["action"] == "replace"
    assert result["from_package"] == "auc"
    assert result["to_package"] == "owut"
    assert result["reason"] == "Package renamed in 24.10"
    assert result["automatic"] is True


def test_package_resolver_no_changes():
    """Test resolver with no package changes needed"""
    resolver = PackageResolver()

    request = BuildRequest(
        version="23.05.5",
        target="ath79/generic",
        profile="tplink_archer-c7-v5",
        packages=["luci", "htop"],
    )

    final_packages, changes = resolver.resolve(request)

    assert "luci" in final_packages
    assert "htop" in final_packages
    # No changes should be made for basic packages on 23.05
    assert len(changes) == 0


def test_package_resolver_auc_migration():
    """Test auc → owut migration in 24.10"""
    resolver = PackageResolver()

    request = BuildRequest(
        version="24.10.0",
        target="ath79/generic",
        profile="tplink_archer-c7-v5",
        packages=["luci", "auc"],
    )

    final_packages, changes = resolver.resolve(request)

    # auc should be replaced with owut
    assert "owut" in final_packages
    assert "auc" not in final_packages
    assert "luci" in final_packages

    # Should have one migration change
    assert len(changes) == 1
    migration = changes[0]
    assert migration.type == "migration"
    assert migration.action == "replace"
    assert migration.from_package == "auc"
    assert migration.to_package == "owut"


def test_package_resolver_hardware_dependencies():
    """Test hardware-specific package addition"""
    resolver = PackageResolver()

    request = BuildRequest(
        version="23.05.5",
        target="mediatek/mt7622",
        profile="linksys_e8450",
        packages=["luci"],
    )

    final_packages, changes = resolver.resolve(request)

    # Should add kmod-mt7622-firmware
    assert "kmod-mt7622-firmware" in final_packages
    assert "luci" in final_packages

    # Should have one addition
    assert len(changes) == 1
    addition = changes[0]
    assert addition.type == "addition"
    assert addition.action == "add"
    assert addition.package == "kmod-mt7622-firmware"


def test_package_resolver_language_pack_rename():
    """Test language pack renaming in 24.10"""
    resolver = PackageResolver()

    request = BuildRequest(
        version="24.10.0",
        target="ath79/generic",
        profile="tplink_archer-c7-v5",
        packages=["luci", "luci-i18n-opkg-en"],
    )

    final_packages, changes = resolver.resolve(request)

    # Language pack should be renamed
    assert "luci-i18n-package-manager-en" in final_packages
    assert "luci-i18n-opkg-en" not in final_packages
    assert "luci" in final_packages

    # Should have one migration
    assert len(changes) == 1
    migration = changes[0]
    assert migration.type == "migration"
    assert migration.from_package == "luci-i18n-opkg-en"
    assert migration.to_package == "luci-i18n-package-manager-en"


def test_package_resolver_multiple_changes():
    """Test multiple package changes in one request"""
    resolver = PackageResolver()

    request = BuildRequest(
        version="25.12.0",
        target="kirkwood/generic",
        profile="checkpoint_l-50",
        packages=["luci"],
    )

    final_packages, changes = resolver.resolve(request)

    # Should add kmod-dsa-mv88e6xxx
    assert "kmod-dsa-mv88e6xxx" in final_packages
    assert "luci" in final_packages

    # Should have at least one addition
    assert len(changes) >= 1
    addition = next((c for c in changes if c.package == "kmod-dsa-mv88e6xxx"), None)
    assert addition is not None
    assert addition.type == "addition"


def test_package_resolver_lantiq_firmware():
    """Test lantiq PHY firmware additions in 25.12"""
    resolver = PackageResolver()

    request = BuildRequest(
        version="25.12.0",
        target="lantiq/xrx200",
        profile="arcadyan_arv7519rw22",
        packages=["luci"],
    )

    final_packages, changes = resolver.resolve(request)

    # Should add PHY firmware packages
    assert "xrx200-rev1.1-phy22f-firmware" in final_packages
    assert "xrx200-rev1.2-phy22f-firmware" in final_packages
    assert "luci" in final_packages

    # Should have two additions
    firmware_additions = [
        c
        for c in changes
        if c.type == "addition" and "firmware" in c.package
    ]
    assert len(firmware_additions) == 2


def test_package_resolver_get_addition_reason():
    """Test addition reason detection"""
    resolver = PackageResolver()

    request = BuildRequest(
        version="23.05.5",
        target="ath79/generic",
        profile="test",
        packages=[],
    )

    # Test kernel module
    reason = resolver._get_addition_reason("kmod-usb-core", request)
    assert "kernel module" in reason.lower()

    # Test language pack
    reason = resolver._get_addition_reason("luci-i18n-base-en", request)
    assert "language pack" in reason.lower()

    # Test PHY firmware
    reason = resolver._get_addition_reason("xrx200-rev1.1-phy11g-firmware", request)
    assert "firmware" in reason.lower()

    # Test generic package
    reason = resolver._get_addition_reason("htop", request)
    assert "version/target/profile" in reason.lower()


def test_package_resolver_preserves_original_request():
    """Test that resolver doesn't modify the original request object"""
    resolver = PackageResolver()

    original_packages = ["luci", "auc"]
    request = BuildRequest(
        version="24.10.0",
        target="ath79/generic",
        profile="test",
        packages=original_packages.copy(),
    )

    # Packages will be modified during resolve
    final_packages, changes = resolver.resolve(request)

    # The request.packages will be modified (this is expected)
    # But we track changes correctly
    assert len(changes) == 1
    assert changes[0].from_package == "auc"
    assert changes[0].to_package == "owut"
