"""Integration tests for the complete prepare workflow"""

import pytest


class TestPrepareIntegration:
    """Integration tests for the complete prepare workflow"""

    def test_complete_prepare_workflow(self, client):
        """Test complete prepare workflow from request to response"""
        request = {
            "version": "24.10.0",
            "target": "ath79/generic",
            "profile": "tplink_tl-wdr4300-v1",
            "packages": ["luci", "auc", "luci-i18n-opkg-en"],
        }

        response = client.post("/api/v1/prepare", json=request)

        assert response.status_code == 200
        data = response.json()

        # Should have migrated packages
        assert "auc" not in data["resolved_packages"]
        assert "owut" in data["resolved_packages"]
        assert "luci-i18n-opkg-en" not in data["resolved_packages"]
        assert "luci-i18n-package-manager-en" in data["resolved_packages"]

        # Should track changes
        assert len(data["changes"]) >= 2

        # Should have prepared request ready to send to build service
        assert data["prepared_request"]["version"] == "24.10.0"
        assert "owut" in data["prepared_request"]["packages"]
        assert "auc" not in data["prepared_request"]["packages"]

    def test_hardware_specific_workflow(self, client):
        """Test workflow with hardware-specific additions"""
        request = {
            "version": "25.12.0",
            "target": "kirkwood/generic",
            "profile": "checkpoint_l-50",
            "packages": ["luci"],
        }

        response = client.post("/api/v1/prepare", json=request)

        assert response.status_code == 200
        data = response.json()

        # Should have added hardware-specific module
        assert "kmod-dsa-mv88e6xxx" in data["resolved_packages"]

        # Should track the addition
        additions = [c for c in data["changes"] if c["type"] == "addition"]
        assert len(additions) >= 1

    def test_multiple_changes_workflow(self, client):
        """Test workflow with multiple types of changes"""
        request = {
            "version": "25.12.0",
            "target": "lantiq/xrx200",
            "profile": "arcadyan_arv7519rw22",
            "packages": ["luci"],
        }

        response = client.post("/api/v1/prepare", json=request)

        assert response.status_code == 200
        data = response.json()

        # Should have added PHY firmware packages
        assert "xrx200-rev1.1-phy22f-firmware" in data["resolved_packages"]
        assert "xrx200-rev1.2-phy22f-firmware" in data["resolved_packages"]

        # Should track multiple additions
        additions = [c for c in data["changes"] if c["type"] == "addition"]
        assert len(additions) >= 2

    def test_prepare_then_build_workflow_simulation(self, client):
        """Simulate prepare -> build workflow"""
        # Step 1: Prepare the request
        original_request = {
            "version": "24.10.0",
            "target": "ath79/generic",
            "profile": "test,device",  # Will be sanitized
            "packages": ["luci", "auc"],
            "diff_packages": True,
        }

        prepare_response = client.post("/api/v1/prepare", json=original_request)
        assert prepare_response.status_code == 200
        prepare_data = prepare_response.json()

        # Step 2: Get the prepared request
        prepared_request = prepare_data["prepared_request"]

        # Verify prepared request is ready for build
        assert prepared_request["profile"] == "test_device"  # Sanitized
        assert "owut" in prepared_request["packages"]  # Migrated
        assert "auc" not in prepared_request["packages"]  # Removed

        # Step 3: Verify request hash for caching
        request_hash = prepare_data["request_hash"]
        assert len(request_hash) == 64

    def test_idempotent_prepare(self, client):
        """Preparing the same request twice should give same results"""
        request = {
            "version": "24.10.0",
            "target": "ath79/generic",
            "profile": "test",
            "packages": ["luci", "auc"],
        }

        response1 = client.post("/api/v1/prepare", json=request)
        response2 = client.post("/api/v1/prepare", json=request)

        data1 = response1.json()
        data2 = response2.json()

        assert data1["resolved_packages"] == data2["resolved_packages"]
        assert data1["request_hash"] == data2["request_hash"]
        assert len(data1["changes"]) == len(data2["changes"])

    def test_from_version_preserved(self, client):
        """from_version should be preserved in prepared request"""
        request = {
            "version": "24.10.0",
            "from_version": "23.05.0",
            "target": "ath79/generic",
            "profile": "test",
            "packages": ["luci"],
        }

        response = client.post("/api/v1/prepare", json=request)
        data = response.json()

        assert data["prepared_request"]["from_version"] == "23.05.0"

    def test_build_specific_fields_not_in_prepare(self, client):
        """Build-specific fields should NOT be in prepared request"""
        request = {
            "version": "23.05.5",
            "target": "ath79/generic",
            "profile": "test",
            "packages": ["luci"],
        }

        response = client.post("/api/v1/prepare", json=request)
        data = response.json()

        prepared = data["prepared_request"]
        
        # Prepare service should NOT include build-specific fields
        assert "rootfs_size_mb" not in prepared
        assert "repositories" not in prepared
        assert "repository_keys" not in prepared
        assert "client" not in prepared
        assert "diff_packages" not in prepared
        
        # Should only have minimal fields needed for package resolution
        assert "version" in prepared
        assert "target" in prepared
        assert "profile" in prepared
        assert "packages" in prepared


class TestServiceIndependence:
    """Tests to verify service independence"""

    def test_no_redis_dependency(self, client):
        """Prepare service should work without Redis"""
        # This test verifies that no Redis connection is attempted
        request = {
            "version": "23.05.5",
            "target": "ath79/generic",
            "profile": "test",
            "packages": ["luci"],
        }

        # Should succeed even though no Redis is available
        response = client.post("/api/v1/prepare", json=request)
        assert response.status_code == 200

    def test_no_build_execution(self, client):
        """Prepare service should not execute builds"""
        # Verify capabilities show build_execution: False
        response = client.get("/api/v1/status")
        data = response.json()

        assert data["capabilities"]["build_execution"] is False

    def test_no_caching(self, client):
        """Prepare service should not handle caching"""
        # Verify capabilities show caching: False
        response = client.get("/api/v1/status")
        data = response.json()

        assert data["capabilities"]["caching"] is False

    def test_stateless_operation(self, client):
        """Prepare service should be stateless"""
        # Same request should produce same response regardless of order
        request1 = {
            "version": "24.10.0",
            "target": "ath79/generic",
            "profile": "test1",
            "packages": ["luci"],
        }
        request2 = {
            "version": "23.05.5",
            "target": "x86/64",
            "profile": "test2",
            "packages": ["vim"],
        }

        # Process in one order
        r1a = client.post("/api/v1/prepare", json=request1)
        r2a = client.post("/api/v1/prepare", json=request2)

        # Process in reverse order
        r2b = client.post("/api/v1/prepare", json=request2)
        r1b = client.post("/api/v1/prepare", json=request1)

        # Results should be identical
        assert r1a.json()["request_hash"] == r1b.json()["request_hash"]
        assert r2a.json()["request_hash"] == r2b.json()["request_hash"]
