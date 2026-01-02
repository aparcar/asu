# ASU Prepare Service Tests

Comprehensive test suite for the asu-prepare microservice.

## Test Structure

```
tests/
├── __init__.py                    # Test package initialization
├── conftest.py                    # Pytest fixtures and configuration
├── test_api.py                    # FastAPI endpoint tests
├── test_build_request.py          # BuildRequest model validation tests
├── test_package_resolution.py     # Package resolution logic tests
├── test_package_changes.py        # Package changes logic tests
└── test_integration.py            # Integration and workflow tests
```

## Running Tests

### Run all tests
```bash
cd asu-prepare
pytest
```

### Run specific test file
```bash
pytest tests/test_api.py
```

### Run specific test class
```bash
pytest tests/test_api.py::TestPrepareEndpoint
```

### Run specific test
```bash
pytest tests/test_api.py::TestPrepareEndpoint::test_prepare_basic_request
```

### Run with verbose output
```bash
pytest -v
```

### Run with coverage
```bash
pytest --cov=. --cov-report=html
```

## Test Categories

### API Tests (`test_api.py`)
- Root endpoint functionality
- Health check endpoint
- Prepare endpoint validation and responses
- Status endpoint capabilities
- Request/response formats
- Error handling

### Build Request Tests (`test_build_request.py`)
- Pydantic model validation
- Required field validation
- Pattern matching (version, target, profile, packages)
- Default values
- Serialization/deserialization

### Package Resolution Tests (`test_package_resolution.py`)
- Basic package resolution
- Package migrations (e.g., auc → owut)
- Language pack migrations
- Change tracking
- PackageChange model

### Package Changes Tests (`test_package_changes.py`)
- Version-specific changes (23.05, 24.10, 25.12)
- Target-specific additions
- Profile-specific kernel modules
- Hardware-specific firmware
- Language pack replacements

### Integration Tests (`test_integration.py`)
- Complete prepare workflow
- Multi-step changes
- Idempotent operations
- Service independence verification
- Stateless operation verification

## Test Fixtures

### `client`
FastAPI TestClient for making HTTP requests to the service.

### `sample_build_request`
Basic valid build request for testing standard flows.

### `migration_build_request`
Request that triggers auc → owut migration (24.10).

### `language_pack_migration_request`
Request that triggers language pack migration (24.10).

### `hardware_specific_request`
Request for hardware needing additional modules (23.05).

### `dsa_mv88e6xxx_request`
Request needing kmod-dsa-mv88e6xxx (25.12).

### `xrx200_phy_firmware_request`
Request needing XRX200 PHY firmware (25.12).

## Key Testing Principles

1. **Service Independence**: Tests verify the prepare service has no dependencies on Redis, Podman, or build infrastructure.

2. **Stateless Operation**: Tests verify the service is stateless and produces consistent results.

3. **Validation**: Tests ensure Pydantic models properly validate all input fields.

4. **Package Changes**: Tests verify all version/target/profile-specific package changes work correctly.

5. **Migration Tracking**: Tests verify all package changes are properly tracked and reported.

## Adding New Tests

When adding new package changes logic:

1. Add test fixtures in `conftest.py` if needed
2. Add specific test cases in `test_package_changes.py`
3. Add resolution tests in `test_package_resolution.py`
4. Add integration workflow test in `test_integration.py`

Example:
```python
def test_new_version_package_change(self):
    """26.01 should add new-package for specific target"""
    request = BuildRequest(
        version="26.01.0",
        target="new/target",
        profile="test",
        packages=["luci"],
    )
    
    apply_package_changes(request)
    
    assert "new-package" in request.packages
```

## Continuous Integration

These tests are designed to run quickly without external dependencies:
- No Redis required
- No Podman required
- No network requests (all mocked)
- Fast execution (< 1 second total)

Perfect for CI/CD pipelines.
