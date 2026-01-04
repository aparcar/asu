"""Tests for package changes logic"""

import pytest
from prepare_request import PrepareRequest
from package_changes import apply_package_changes


class TestPackageChanges2305:
    """Tests for 23.05 specific package changes"""

    def test_mediatek_mt7622_firmware(self):
        """23.05 mediatek/mt7622 should add kmod-mt7622-firmware"""
        request = PrepareRequest(
            version="23.05.0",
            target="mediatek/mt7622",
            profile="test-device",
            packages=["luci"],
        )

        apply_package_changes(request)

        assert "kmod-mt7622-firmware" in request.packages

    def test_ath79_rtl8366s_switch(self):
        """23.05 ath79 specific profiles should add rtl8366s switch"""
        profiles_needing_switch = [
            "buffalo_wzr-hp-g300nh-s",
            "dlink_dir-825-b1",
            "netgear_wndr3700",
            "netgear_wndr3700-v2",
            "netgear_wndr3800",
        ]

        for profile in profiles_needing_switch:
            request = PrepareRequest(
                version="23.05.0",
                target="ath79/generic",
                profile=profile,
                packages=["luci"],
            )

            apply_package_changes(request)

            assert "kmod-switch-rtl8366s" in request.packages

    def test_ath79_rtl8366rb_switch(self):
        """23.05 buffalo_wzr-hp-g300nh-rb should add rtl8366rb switch"""
        request = PrepareRequest(
            version="23.05.0",
            target="ath79/generic",
            profile="buffalo_wzr-hp-g300nh-rb",
            packages=["luci"],
        )

        apply_package_changes(request)

        assert "kmod-switch-rtl8366rb" in request.packages


class TestPackageChanges2410:
    """Tests for 24.10 specific package changes"""

    def test_auc_to_owut_migration(self):
        """24.10 should migrate auc to owut"""
        request = PrepareRequest(
            version="24.10.0",
            target="ath79/generic",
            profile="test",
            packages=["luci", "auc", "vim"],
        )

        apply_package_changes(request)

        assert "auc" not in request.packages
        assert "owut" in request.packages
        assert "luci" in request.packages
        assert "vim" in request.packages

    def test_auc_migration_snapshot(self):
        """SNAPSHOT should also migrate auc to owut"""
        request = PrepareRequest(
            version="24.10-SNAPSHOT",
            target="ath79/generic",
            profile="test",
            packages=["auc"],
        )

        apply_package_changes(request)

        assert "auc" not in request.packages
        assert "owut" in request.packages

    def test_language_pack_migration(self):
        """24.10 should migrate luci-i18n-opkg-* to luci-i18n-package-manager-*"""
        request = PrepareRequest(
            version="24.10.0",
            target="ath79/generic",
            profile="test",
            packages=["luci-i18n-opkg-en", "luci-i18n-opkg-de"],
        )

        apply_package_changes(request)

        assert "luci-i18n-opkg-en" not in request.packages
        assert "luci-i18n-opkg-de" not in request.packages
        assert "luci-i18n-package-manager-en" in request.packages
        assert "luci-i18n-package-manager-de" in request.packages


class TestPackageChanges2512:
    """Tests for 25.12 specific package changes"""

    def test_kirkwood_dsa_mv88e6xxx(self):
        """25.12 kirkwood specific profiles should add kmod-dsa-mv88e6xxx"""
        profiles = [
            "checkpoint_l-50",
            "endian_4i-edge-200",
            "linksys_e4200-v2",
            "linksys_ea3500",
            "linksys_ea4500",
        ]

        for profile in profiles:
            request = PrepareRequest(
                version="25.12.0",
                target="kirkwood/generic",
                profile=profile,
                packages=["luci"],
            )

            apply_package_changes(request)

            assert "kmod-dsa-mv88e6xxx" in request.packages

    def test_mvebu_cortexa9_dsa_mv88e6xxx(self):
        """25.12 mvebu/cortexa9 specific profiles should add kmod-dsa-mv88e6xxx"""
        profiles = [
            "cznic_turris-omnia",
            "linksys_wrt1200ac",
            "linksys_wrt3200acm",
        ]

        for profile in profiles:
            request = PrepareRequest(
                version="25.12.0",
                target="mvebu/cortexa9",
                profile=profile,
                packages=["luci"],
            )

            apply_package_changes(request)

            assert "kmod-dsa-mv88e6xxx" in request.packages

    def test_lantiq_xrx200_phy22f_firmware(self):
        """25.12 lantiq/xrx200 specific profiles should add phy22f firmware"""
        profiles = [
            "arcadyan_arv7519rw22",
            "arcadyan_vgv7510kw22-brn",
            "avm_fritz7412",
        ]

        for profile in profiles:
            request = PrepareRequest(
                version="25.12.0",
                target="lantiq/xrx200",
                profile=profile,
                packages=["luci"],
            )

            apply_package_changes(request)

            assert "xrx200-rev1.1-phy22f-firmware" in request.packages
            assert "xrx200-rev1.2-phy22f-firmware" in request.packages

    def test_lantiq_xrx200_phy11g_firmware(self):
        """25.12 lantiq/xrx200 specific profiles should add phy11g firmware"""
        profiles = [
            "tplink_vr200",
            "avm_fritz7490",
            "bt_homehub-v5a",
        ]

        for profile in profiles:
            request = PrepareRequest(
                version="25.12.0",
                target="lantiq/xrx200",
                profile=profile,
                packages=["luci"],
            )

            apply_package_changes(request)

            assert "xrx200-rev1.1-phy11g-firmware" in request.packages
            assert "xrx200-rev1.2-phy11g-firmware" in request.packages

    def test_bcm53xx_hci_uart(self):
        """25.12 bcm53xx/generic meraki_mr32 should add kmod-hci-uart"""
        request = PrepareRequest(
            version="25.12.0",
            target="bcm53xx/generic",
            profile="meraki_mr32",
            packages=["luci"],
        )

        apply_package_changes(request)

        assert "kmod-hci-uart" in request.packages

    def test_ipq40xx_hci_uart(self):
        """25.12 ipq40xx/generic linksys_whw03 should add kmod-hci-uart"""
        request = PrepareRequest(
            version="25.12.0",
            target="ipq40xx/generic",
            profile="linksys_whw03",
            packages=["luci"],
        )

        apply_package_changes(request)

        assert "kmod-hci-uart" in request.packages


class TestPackageChangesGeneric:
    """Tests for generic package changes logic"""

    def test_add_if_missing_does_not_duplicate(self):
        """Package should not be added if already present"""
        request = PrepareRequest(
            version="23.05.0",
            target="mediatek/mt7622",
            profile="test",
            packages=["luci", "kmod-mt7622-firmware"],  # Already present
        )

        original_count = len(request.packages)
        apply_package_changes(request)

        # Should not add duplicate
        assert request.packages.count("kmod-mt7622-firmware") == 1
        assert len(request.packages) == original_count

    def test_version_prefix_matching(self):
        """Version matching should work with prefixes"""
        # 23.05.5 should match 23.05
        request = PrepareRequest(
            version="23.05.5",
            target="mediatek/mt7622",
            profile="test",
            packages=["luci"],
        )

        apply_package_changes(request)
        assert "kmod-mt7622-firmware" in request.packages

    def test_no_changes_for_other_targets(self):
        """No changes should be applied for unrelated targets"""
        request = PrepareRequest(
            version="23.05.0",
            target="x86/64",  # No special handling
            profile="generic",
            packages=["luci"],
        )

        original_packages = request.packages.copy()
        apply_package_changes(request)

        assert request.packages == original_packages
