"""Tests for PrepareRequest model validation"""

import pytest
from pydantic import ValidationError
from prepare_request import PrepareRequest


class TestPrepareRequestValidation:
    """Tests for PrepareRequest Pydantic validation"""

    def test_minimal_valid_request(self):
        """Minimal valid request should work"""
        request = PrepareRequest(
            version="23.05.5",
            target="ath79/generic",
            profile="test",
        )

        assert request.version == "23.05.5"
        assert request.target == "ath79/generic"
        assert request.profile == "test"
        assert request.packages == []

    def test_full_valid_request(self):
        """Full valid request with all fields should work"""
        request = PrepareRequest(
            distro="openwrt",
            version="23.05.5",
            from_version="23.05.0",
            target="ath79/generic",
            profile="tplink_tl-wdr4300-v1",
            packages=["luci", "vim", "tmux"],
        )

        assert request.distro == "openwrt"
        assert request.from_version == "23.05.0"
        assert len(request.packages) == 3

    def test_default_values(self):
        """Default values should be set correctly"""
        request = PrepareRequest(
            version="23.05.5",
            target="ath79/generic",
            profile="test",
        )

        assert request.distro == "openwrt"
        assert request.from_version is None
        assert request.packages == []

    def test_missing_required_field(self):
        """Missing required field should raise ValidationError"""
        with pytest.raises(ValidationError):
            PrepareRequest(
                version="23.05.5",
                # Missing target and profile
            )

    def test_invalid_version_pattern(self):
        """Invalid version pattern should raise ValidationError"""
        with pytest.raises(ValidationError):
            PrepareRequest(
                version="23.05.5 invalid",  # Space not allowed
                target="ath79/generic",
                profile="test",
            )

    def test_invalid_target_pattern(self):
        """Invalid target pattern should raise ValidationError"""
        with pytest.raises(ValidationError):
            PrepareRequest(
                version="23.05.5",
                target="invalid",  # Must be format: arch/subarch
                profile="test",
            )

    def test_invalid_profile_pattern(self):
        """Invalid profile pattern should raise ValidationError"""
        with pytest.raises(ValidationError):
            PrepareRequest(
                version="23.05.5",
                target="ath79/generic",
                profile="test profile",  # Space not allowed
            )

    def test_invalid_package_pattern(self):
        """Invalid package name pattern should raise ValidationError"""
        with pytest.raises(ValidationError):
            PrepareRequest(
                version="23.05.5",
                target="ath79/generic",
                profile="test",
                packages=["vim", "invalid package"],  # Space not allowed
            )

    def test_valid_package_patterns(self):
        """Valid package name patterns should work"""
        request = PrepareRequest(
            version="23.05.5",
            target="ath79/generic",
            profile="test",
            packages=["vim", "luci-i18n-base-en", "kmod-usb-core", "lib.so.1"],
        )

        assert len(request.packages) == 4

    def test_snapshot_version(self):
        """SNAPSHOT version should be valid"""
        request = PrepareRequest(
            version="SNAPSHOT",
            target="ath79/generic",
            profile="test",
        )

        assert request.version == "SNAPSHOT"


class TestPrepareRequestSerialization:
    """Tests for PrepareRequest serialization"""

    def test_model_dump(self):
        """model_dump should produce dictionary"""
        request = PrepareRequest(
            version="23.05.5",
            target="ath79/generic",
            profile="test",
            packages=["luci", "vim"],
        )

        data = request.model_dump()

        assert isinstance(data, dict)
        assert data["version"] == "23.05.5"
        assert data["target"] == "ath79/generic"
        assert data["packages"] == ["luci", "vim"]

    def test_model_dump_json(self):
        """model_dump_json should produce JSON string"""
        request = PrepareRequest(
            version="23.05.5",
            target="ath79/generic",
            profile="test",
        )

        json_str = request.model_dump_json()

        assert isinstance(json_str, str)
        assert "23.05.5" in json_str
        assert "ath79/generic" in json_str
