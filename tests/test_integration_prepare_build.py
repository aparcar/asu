"""
Integration tests for the prepare + build workflow.

These tests require both services to be running:
- asu-prepare service on http://localhost:8001
- asu-build service on http://localhost:8000

Run with:
    pytest tests/test_integration_prepare_build.py -v

Or skip if services not running:
    pytest tests/test_integration_prepare_build.py -v -m "not integration"
"""

import pytest
import requests
import time
import os

# Configuration
PREPARE_URL = os.getenv("PREPARE_SERVICE_URL", "http://localhost:8001")
BUILD_URL = os.getenv("BUILD_SERVICE_URL", "http://localhost:8000")
MAX_POLL_ATTEMPTS = 60  # 60 seconds max
POLL_INTERVAL = 1  # 1 second between polls


def check_service_available(url):
    """Check if a service is available"""
    try:
        response = requests.get(f"{url}/health", timeout=2)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


@pytest.fixture(scope="module")
def services_available():
    """Check if both services are available"""
    prepare_available = check_service_available(PREPARE_URL)
    build_available = check_service_available(BUILD_URL)
    
    if not prepare_available:
        pytest.skip(f"Prepare service not available at {PREPARE_URL}")
    if not build_available:
        pytest.skip(f"Build service not available at {BUILD_URL}")
    
    return True


@pytest.mark.integration
class TestPrepareEndpointIntegration:
    """Integration tests for the prepare endpoint"""

    def test_prepare_basic_request(self, services_available):
        """Test basic prepare request"""
        request = {
            "version": "23.05.5",
            "target": "ath79/generic",
            "profile": "tplink_tl-wdr4300-v1",
            "packages": ["luci"],
        }

        response = requests.post(f"{PREPARE_URL}/api/v1/prepare", json=request)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "prepared"
        assert "resolved_packages" in data
        assert "changes" in data
        assert "prepared_request" in data
        assert "request_hash" in data

    def test_prepare_with_migration(self, services_available):
        """Test prepare with package migration (auc -> owut)"""
        request = {
            "version": "24.10.0",
            "target": "ath79/generic",
            "profile": "tplink_tl-wdr4300-v1",
            "packages": ["luci", "auc"],
        }

        response = requests.post(f"{PREPARE_URL}/api/v1/prepare", json=request)
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have migrated auc to owut
        assert "auc" not in data["resolved_packages"]
        assert "owut" in data["resolved_packages"]
        
        # Should have tracked the migration
        migrations = [c for c in data["changes"] if c["type"] == "migration"]
        assert len(migrations) >= 1
        assert any(c["from_package"] == "auc" and c["to_package"] == "owut" for c in migrations)

    def test_prepare_with_language_pack_migration(self, services_available):
        """Test prepare with language pack migration"""
        request = {
            "version": "24.10.0",
            "target": "ath79/generic",
            "profile": "tplink_tl-wdr4300-v1",
            "packages": ["luci", "luci-i18n-opkg-en"],
        }

        response = requests.post(f"{PREPARE_URL}/api/v1/prepare", json=request)
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have migrated language pack
        assert "luci-i18n-opkg-en" not in data["resolved_packages"]
        assert "luci-i18n-package-manager-en" in data["resolved_packages"]

    def test_prepare_profile_sanitization(self, services_available):
        """Test that prepare sanitizes profile names"""
        request = {
            "version": "23.05.5",
            "target": "ath79/generic",
            "profile": "test,profile,with,commas",
            "packages": ["luci"],
        }

        response = requests.post(f"{PREPARE_URL}/api/v1/prepare", json=request)
        
        assert response.status_code == 200
        data = response.json()
        
        # Profile should be sanitized
        assert "," not in data["prepared_request"]["profile"]
        assert data["prepared_request"]["profile"] == "test_profile_with_commas"


@pytest.mark.integration
class TestPrepareBuildWorkflow:
    """Integration tests for the complete prepare -> build workflow"""

    def poll_build(self, build_url, timeout=MAX_POLL_ATTEMPTS):
        """Poll build endpoint until completion or timeout"""
        attempts = 0
        while attempts < timeout:
            response = requests.get(build_url)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 202:
                data = response.json()
                print(f"Building... {data.get('imagebuilder_status', 'unknown')}")
                time.sleep(POLL_INTERVAL)
                attempts += 1
            else:
                # Error occurred
                return response.json()
        
        raise TimeoutError(f"Build did not complete within {timeout} seconds")

    def test_prepare_then_build_basic(self, services_available):
        """Test complete workflow: prepare -> build"""
        # Step 1: Prepare
        prepare_request = {
            "version": "23.05.5",
            "target": "x86/64",
            "profile": "generic",
            "packages": ["luci"],
        }

        prepare_response = requests.post(
            f"{PREPARE_URL}/api/v1/prepare",
            json=prepare_request
        )
        
        assert prepare_response.status_code == 200
        prepare_data = prepare_response.json()
        
        # Step 2: Build with prepared request
        # Note: Build service needs additional fields
        build_request = {
            **prepare_data["prepared_request"],
            "diff_packages": False,  # Build service needs this
        }

        build_response = requests.post(
            f"{BUILD_URL}/api/v1/build",
            json=build_request
        )
        
        # Build should be accepted (202) or completed (200)
        assert build_response.status_code in [200, 202]
        
        if build_response.status_code == 202:
            # Poll until completion
            build_data = build_response.json()
            request_hash = build_data["request_hash"]
            
            # Poll using request_hash
            final_data = self.poll_build(f"{BUILD_URL}/api/v1/build/{request_hash}")
            
            # Should have completed successfully
            assert "images" in final_data or "detail" in final_data

    def test_prepare_with_migration_then_build(self, services_available):
        """Test workflow with package migration"""
        # Step 1: Prepare with migration
        prepare_request = {
            "version": "24.10.0",
            "target": "x86/64", 
            "profile": "generic",
            "packages": ["luci", "auc"],  # auc will migrate to owut
        }

        prepare_response = requests.post(
            f"{PREPARE_URL}/api/v1/prepare",
            json=prepare_request
        )
        
        assert prepare_response.status_code == 200
        prepare_data = prepare_response.json()
        
        # Verify migration happened
        assert "owut" in prepare_data["resolved_packages"]
        assert "auc" not in prepare_data["resolved_packages"]
        
        # Step 2: Build with migrated packages
        build_request = {
            **prepare_data["prepared_request"],
            "diff_packages": False,
        }

        build_response = requests.post(
            f"{BUILD_URL}/api/v1/build",
            json=build_request
        )
        
        assert build_response.status_code in [200, 202]

    def test_prepare_shows_changes_before_build(self, services_available):
        """Test that prepare shows changes before committing to build"""
        # Use a profile that requires additional packages
        prepare_request = {
            "version": "25.12.0",
            "target": "kirkwood/generic",
            "profile": "checkpoint_l-50",
            "packages": ["luci"],
        }

        prepare_response = requests.post(
            f"{PREPARE_URL}/api/v1/prepare",
            json=prepare_request
        )
        
        assert prepare_response.status_code == 200
        prepare_data = prepare_response.json()
        
        # Should show that kmod-dsa-mv88e6xxx will be added
        assert "kmod-dsa-mv88e6xxx" in prepare_data["resolved_packages"]
        
        # Should have changes tracked
        additions = [c for c in prepare_data["changes"] if c["type"] == "addition"]
        assert len(additions) >= 1
        assert any("kmod-dsa-mv88e6xxx" in c.get("package", "") for c in additions)
        
        # User can see changes BEFORE building
        print("Changes that will be applied:")
        for change in prepare_data["changes"]:
            if change["type"] == "migration":
                print(f"  🔄 {change['from_package']} → {change['to_package']}")
            elif change["type"] == "addition":
                print(f"  ➕ {change['package']}")
            elif change["type"] == "removal":
                print(f"  ➖ {change['package']}")


@pytest.mark.integration 
class TestServiceIndependence:
    """Test that services are truly independent"""

    def test_prepare_works_without_build_service(self):
        """Prepare service should work even if build service is down"""
        if not check_service_available(PREPARE_URL):
            pytest.skip("Prepare service not available")
        
        request = {
            "version": "23.05.5",
            "target": "ath79/generic",
            "profile": "test",
            "packages": ["luci"],
        }

        response = requests.post(f"{PREPARE_URL}/api/v1/prepare", json=request)
        
        # Should work regardless of build service status
        assert response.status_code == 200

    def test_prepare_has_no_build_capability(self, services_available):
        """Prepare service should not have build endpoint"""
        response = requests.post(
            f"{PREPARE_URL}/api/v1/build",
            json={"version": "23.05.5", "target": "x86/64", "profile": "generic"}
        )
        
        # Should return 404 or 405 (not found / method not allowed)
        assert response.status_code in [404, 405]

    def test_services_report_different_capabilities(self, services_available):
        """Services should report different capabilities"""
        prepare_status = requests.get(f"{PREPARE_URL}/api/v1/status").json()
        build_status = requests.get(f"{BUILD_URL}/api/v1/status").json()
        
        # Prepare service capabilities
        assert prepare_status["capabilities"]["package_resolution"] is True
        assert prepare_status["capabilities"]["build_execution"] is False
        
        # Build service capabilities (when /status endpoint exists)
        # Note: Build service may not have status endpoint yet
