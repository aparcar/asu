"""Tests for package resolution logic"""

import pytest
from prepare_request import PrepareRequest
from package_resolution import PackageResolver, PackageChange


class TestPackageResolver:
    """Tests for the PackageResolver class"""

    def test_resolver_basic_resolution(self):
        """Resolver should handle basic package resolution"""
        resolver = PackageResolver()
        request = PrepareRequest(
            version="23.05.5",
            target="ath79/generic",
            profile="test",
            packages=["luci", "vim"],
        )

        final_packages, changes = resolver.resolve(request)

        assert isinstance(final_packages, list)
        assert isinstance(changes, list)
        assert "luci" in final_packages
        assert "vim" in final_packages

    def test_resolver_no_changes(self):
        """Resolver should return empty changes when nothing changes"""
        resolver = PackageResolver()
        request = PrepareRequest(
            version="23.05.5",
            target="ath79/generic",
            profile="test",
            packages=["luci"],
        )

        final_packages, changes = resolver.resolve(request)

        # For basic packages with no special handling, no changes expected
        assert len(changes) == 0
        assert final_packages == ["luci"]

    def test_resolver_auc_migration(self):
        """Resolver should migrate auc to owut in 24.10"""
        resolver = PackageResolver()
        request = PrepareRequest(
            version="24.10.0",
            target="ath79/generic",
            profile="test",
            packages=["luci", "auc"],
        )

        final_packages, changes = resolver.resolve(request)

        # auc should be removed
        assert "auc" not in final_packages
        # owut should be added
        assert "owut" in final_packages
        # Should track the migration
        assert len(changes) >= 1
        migration = next((c for c in changes if c.type == "migration"), None)
        assert migration is not None
        assert migration.from_package == "auc"
        assert migration.to_package == "owut"

    def test_resolver_language_pack_migration(self):
        """Resolver should migrate language packs in 24.10"""
        resolver = PackageResolver()
        request = PrepareRequest(
            version="24.10.0",
            target="ath79/generic",
            profile="test",
            packages=["luci", "luci-i18n-opkg-en"],
        )

        final_packages, changes = resolver.resolve(request)

        # Old language pack should be replaced
        assert "luci-i18n-opkg-en" not in final_packages
        # New language pack should be present
        assert "luci-i18n-package-manager-en" in final_packages

    def test_resolver_multiple_language_packs(self):
        """Resolver should migrate multiple language packs"""
        resolver = PackageResolver()
        request = PrepareRequest(
            version="24.10.0",
            target="ath79/generic",
            profile="test",
            packages=["luci-i18n-opkg-en", "luci-i18n-opkg-de", "luci-i18n-opkg-fr"],
        )

        final_packages, changes = resolver.resolve(request)

        # All old language packs should be replaced
        assert "luci-i18n-opkg-en" not in final_packages
        assert "luci-i18n-opkg-de" not in final_packages
        assert "luci-i18n-opkg-fr" not in final_packages
        # New ones should be present
        assert "luci-i18n-package-manager-en" in final_packages
        assert "luci-i18n-package-manager-de" in final_packages
        assert "luci-i18n-package-manager-fr" in final_packages


class TestPackageChange:
    """Tests for the PackageChange class"""

    def test_package_change_to_dict(self):
        """PackageChange should convert to dictionary"""
        change = PackageChange(
            change_type="migration",
            action="replace",
            from_package="auc",
            to_package="owut",
            reason="Package renamed",
            automatic=True,
        )

        result = change.to_dict()

        assert result["type"] == "migration"
        assert result["action"] == "replace"
        assert result["from_package"] == "auc"
        assert result["to_package"] == "owut"
        assert result["reason"] == "Package renamed"
        assert result["automatic"] is True

    def test_package_change_optional_fields(self):
        """PackageChange should handle optional fields"""
        change = PackageChange(
            change_type="addition",
            action="add",
            package="vim",
            reason="User requested",
        )

        result = change.to_dict()

        assert "package" in result
        assert "from_package" not in result
        assert "to_package" not in result
