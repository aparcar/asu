"""Test configuration and fixtures for asu-prepare service"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """FastAPI test client"""
    from main import app

    return TestClient(app)


@pytest.fixture
def sample_build_request():
    """Sample valid build request"""
    return {
        "version": "23.05.5",
        "target": "ath79/generic",
        "profile": "tplink_tl-wdr4300-v1",
        "packages": ["luci", "vim"],
    }


@pytest.fixture
def migration_build_request():
    """Build request that triggers package migrations"""
    return {
        "version": "24.10.0",
        "target": "ath79/generic",
        "profile": "tplink_tl-wdr4300-v1",
        "packages": ["luci", "auc"],  # auc should migrate to owut in 24.10
    }


@pytest.fixture
def language_pack_migration_request():
    """Build request that triggers language pack migration"""
    return {
        "version": "24.10.0",
        "target": "ath79/generic",
        "profile": "tplink_tl-wdr4300-v1",
        "packages": ["luci", "luci-i18n-opkg-en"],  # Should migrate to luci-i18n-package-manager-en
    }


@pytest.fixture
def hardware_specific_request():
    """Build request for hardware that needs additional modules (23.05)"""
    return {
        "version": "23.05.0",
        "target": "mediatek/mt7622",
        "profile": "test-device",
        "packages": ["luci"],
    }


@pytest.fixture
def dsa_mv88e6xxx_request():
    """Build request that needs kmod-dsa-mv88e6xxx (25.12)"""
    return {
        "version": "25.12.0",
        "target": "kirkwood/generic",
        "profile": "checkpoint_l-50",
        "packages": ["luci"],
    }


@pytest.fixture
def xrx200_phy_firmware_request():
    """Build request that needs XRX200 PHY firmware (25.12)"""
    return {
        "version": "25.12.0",
        "target": "lantiq/xrx200",
        "profile": "arcadyan_arv7519rw22",
        "packages": ["luci"],
    }
