"""Tests for the FastAPI endpoints"""

import pytest


class TestRootEndpoint:
    """Tests for the root endpoint"""

    def test_root_returns_service_info(self, client):
        """Root endpoint should return service information"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "asu-prepare"
        assert "version" in data
        assert data["status"] == "running"
        assert "endpoints" in data

    def test_root_lists_endpoints(self, client):
        """Root endpoint should list available endpoints"""
        response = client.get("/")
        data = response.json()
        assert "prepare" in data["endpoints"]
        assert "health" in data["endpoints"]


class TestHealthCheck:
    """Tests for the health check endpoint"""

    def test_health_check_returns_healthy(self, client):
        """Health check should return healthy status"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "asu-prepare"


class TestPrepareEndpoint:
    """Tests for the /api/v1/prepare endpoint"""

    def test_prepare_basic_request(self, client, sample_build_request):
        """Prepare endpoint should accept valid build request"""
        response = client.post("/api/v1/prepare", json=sample_build_request)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "prepared"
        assert "resolved_packages" in data
        assert "changes" in data
        assert "prepared_request" in data
        assert "request_hash" in data

    def test_prepare_preserves_original_packages(self, client, sample_build_request):
        """Prepare endpoint should preserve original package list"""
        response = client.post("/api/v1/prepare", json=sample_build_request)
        data = response.json()
        assert data["original_packages"] == sample_build_request["packages"]

    def test_prepare_sanitizes_profile(self, client):
        """Prepare endpoint should sanitize profile names"""
        request = {
            "version": "23.05.5",
            "target": "ath79/generic",
            "profile": "test,profile,with,commas",
            "packages": ["luci"],
        }
        response = client.post("/api/v1/prepare", json=request)
        assert response.status_code == 200
        data = response.json()
        # Profile should have commas replaced with underscores
        assert "," not in data["prepared_request"]["profile"]
        assert data["prepared_request"]["profile"] == "test_profile_with_commas"

    def test_prepare_returns_only_minimal_fields(self, client):
        """Prepared request should only contain minimal fields needed for migration"""
        request = {
            "version": "23.05.5",
            "target": "ath79/generic",
            "profile": "test",
            "packages": ["luci"],
        }
        response = client.post("/api/v1/prepare", json=request)
        data = response.json()
        prepared = data["prepared_request"]
        
        # Should have minimal fields
        assert "version" in prepared
        assert "target" in prepared
        assert "profile" in prepared
        assert "packages" in prepared
        
        # Should NOT have build-specific fields
        assert "diff_packages" not in prepared
        assert "rootfs_size_mb" not in prepared
        assert "repositories" not in prepared
        assert "repository_keys" not in prepared

    def test_prepare_returns_hash(self, client, sample_build_request):
        """Prepare endpoint should return request hash"""
        response = client.post("/api/v1/prepare", json=sample_build_request)
        data = response.json()
        assert "request_hash" in data
        assert len(data["request_hash"]) == 64  # SHA256 hash

    def test_prepare_same_request_same_hash(self, client, sample_build_request):
        """Same request should produce same hash"""
        response1 = client.post("/api/v1/prepare", json=sample_build_request)
        response2 = client.post("/api/v1/prepare", json=sample_build_request)
        hash1 = response1.json()["request_hash"]
        hash2 = response2.json()["request_hash"]
        assert hash1 == hash2

    def test_prepare_invalid_request(self, client):
        """Invalid request should return validation error"""
        invalid_request = {
            "version": "23.05.5",
            # Missing required fields
        }
        response = client.post("/api/v1/prepare", json=invalid_request)
        assert response.status_code == 422  # Validation error

    def test_prepare_invalid_pattern(self, client):
        """Request with invalid pattern should fail validation"""
        invalid_request = {
            "version": "23.05.5",
            "target": "invalid target",  # Space not allowed
            "profile": "test",
            "packages": ["luci"],
        }
        response = client.post("/api/v1/prepare", json=invalid_request)
        assert response.status_code == 422


class TestStatusEndpoint:
    """Tests for the /api/v1/status endpoint"""

    def test_status_returns_service_info(self, client):
        """Status endpoint should return service information"""
        response = client.get("/api/v1/status")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "asu-prepare"
        assert data["status"] == "operational"

    def test_status_lists_capabilities(self, client):
        """Status endpoint should list service capabilities"""
        response = client.get("/api/v1/status")
        data = response.json()
        capabilities = data["capabilities"]
        # Prepare service can do these
        assert capabilities["package_resolution"] is True
        assert capabilities["package_migration"] is True
        assert capabilities["request_validation"] is True
        # But NOT these (build service responsibilities)
        assert capabilities["build_execution"] is False
        assert capabilities["caching"] is False
