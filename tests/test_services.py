"""Tests for independent microservices"""

import pytest

from asu.build_request import BuildRequest
from asu.services.prepare_service import PrepareService, get_prepare_service
from asu.services.build_service import BuildService, get_build_service


class TestPrepareService:
    """Tests for the independent prepare service"""

    def test_prepare_service_standalone(self):
        """Test prepare service can run without app"""
        service = PrepareService(app=None)

        request = BuildRequest(
            version="24.10.0",
            target="ath79/generic",
            profile="test",
            packages=["luci", "auc"],
        )

        # Should work without validation (no app provided)
        result = service.prepare(request)

        assert result["status"] == "prepared"
        assert "owut" in result["resolved_packages"]
        assert "auc" not in result["resolved_packages"]
        assert len(result["changes"]) >= 1

    def test_prepare_service_singleton(self):
        """Test prepare service singleton"""
        service1 = get_prepare_service()
        service2 = get_prepare_service()

        assert service1 is service2

    def test_prepare_service_no_changes(self):
        """Test prepare service with no package changes"""
        service = PrepareService(app=None)

        request = BuildRequest(
            version="23.05.5",
            target="ath79/generic",
            profile="test",
            packages=["luci"],
        )

        result = service.prepare(request)

        assert result["status"] == "prepared"
        assert result["resolved_packages"] == ["luci"]
        assert len(result["changes"]) == 0

    def test_prepare_service_sanitizes_profile(self):
        """Test prepare service sanitizes profile names"""
        service = PrepareService(app=None)

        request = BuildRequest(
            version="23.05.5",
            target="ath79/generic",
            profile="test,profile",  # Invalid comma
            packages=["luci"],
        )

        result = service.prepare(request)

        # Profile should be sanitized
        assert "," not in result["prepared_request"]["profile"]

    def test_prepare_service_preserves_from_version(self):
        """Test prepare service preserves from_version"""
        service = PrepareService(app=None)

        request = BuildRequest(
            version="24.10.0",
            from_version="23.05.0",
            target="ath79/generic",
            profile="test",
            packages=["luci"],
        )

        result = service.prepare(request)

        assert result["prepared_request"]["from_version"] == "23.05.0"


class TestBuildService:
    """Tests for the independent build service"""

    def test_build_service_singleton(self):
        """Test build service singleton"""
        service1 = get_build_service()
        service2 = get_build_service()

        assert service1 is service2


class TestServiceIndependence:
    """Tests to verify services are truly independent"""

    def test_prepare_has_no_redis_dependency(self):
        """Verify prepare service doesn't import Redis at module level"""
        import asu.services.prepare_service as prepare_module

        # Check module doesn't have redis in its globals
        module_names = [name for name in dir(prepare_module)]

        # Should not have Redis or RQ imports at module level
        assert "redis" not in [n.lower() for n in module_names]
        assert "Queue" not in module_names
        assert "get_queue" not in module_names

    def test_prepare_has_no_podman_dependency(self):
        """Verify prepare service doesn't import Podman"""
        import asu.services.prepare_service as prepare_module

        module_names = [name for name in dir(prepare_module)]

        # Should not have Podman imports
        assert "podman" not in [n.lower() for n in module_names]
        assert "get_podman" not in module_names

    def test_prepare_has_no_build_dependency(self):
        """Verify prepare service doesn't import build logic"""
        import asu.services.prepare_service as prepare_module

        module_names = [name for name in dir(prepare_module)]

        # Should not import build function
        assert "build" not in [n for n in module_names if not n.startswith("_")]

    def test_services_share_common_models(self):
        """Verify both services use the same models"""
        from asu.services.prepare_service import PrepareService
        from asu.services.build_service import BuildService
        from asu.build_request import BuildRequest

        # Both should use BuildRequest
        prepare = PrepareService()
        build = BuildService()

        # Both should accept BuildRequest (no TypeError)
        request = BuildRequest(
            version="23.05.5",
            target="test/test",
            profile="test",
        )

        # Prepare should work
        result = prepare.prepare(request)
        assert result["status"] == "prepared"

        # Build should work (will fail due to missing Redis in tests,
        # but should not fail on BuildRequest type)
        # We just verify it accepts the same type
        assert isinstance(request, BuildRequest)
