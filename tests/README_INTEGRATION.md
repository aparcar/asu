# Integration Tests for ASU Prepare + Build Workflow

This directory contains integration tests and tools for testing the two-step prepare/build workflow.

## Prerequisites

1. **Running Services**:
   - Prepare service at `http://localhost:8001`
   - Build service at `http://localhost:8000`

2. **Python Dependencies**:
   ```bash
   pip install requests pytest
   ```

## Test Files

### Integration Test Suite

**`test_integration_prepare_build.py`** - Comprehensive integration tests

Run all integration tests:
```bash
pytest tests/test_integration_prepare_build.py -v
```

Run only if services are available:
```bash
pytest tests/test_integration_prepare_build.py -v -m integration
```

### Interactive Client

**`uclient.py`** - Interactive command-line client for testing

Usage:
```bash
# Two-step workflow (default - shows changes before building)
python tests/uclient.py tests/configs/basic_build.json

# Prepare-only mode (see changes without building)
python tests/uclient.py tests/configs/migration_auc_to_owut.json --prepare-only

# Legacy single-step workflow (bypasses prepare)
python tests/uclient.py tests/configs/basic_build.json --legacy
```

## Test Configurations

The `configs/` directory contains test scenarios:

### Basic Tests

- **`basic_build.json`** - Simple build with no migrations
- **`migration_auc_to_owut.json`** - Tests auc → owut migration (24.10)
- **`language_pack_migration.json`** - Tests language pack migration (24.10)
- **`hardware_specific.json`** - Tests hardware-specific package addition (25.12)

### Running Examples

1. **See package changes without building**:
   ```bash
   python tests/uclient.py tests/configs/migration_auc_to_owut.json --prepare-only
   ```
   
   Output:
   ```
   📝 Preparing build request...
   ✅ Preparation complete!
   📦 Package changes (1):
     🔄 Migration: auc → owut
        Reason: Package renamed in 24.10.0
   ```

2. **Full build with migration**:
   ```bash
   python tests/uclient.py tests/configs/migration_auc_to_owut.json
   ```
   
   You'll see the changes and be asked to confirm before building.

3. **Hardware-specific packages**:
   ```bash
   python tests/uclient.py tests/configs/hardware_specific.json --prepare-only
   ```
   
   Shows that `kmod-dsa-mv88e6xxx` will be added automatically.

## Integration Test Scenarios

The test suite covers:

### Prepare Endpoint Tests
- ✅ Basic prepare requests
- ✅ Package migrations (auc → owut)
- ✅ Language pack migrations
- ✅ Profile name sanitization
- ✅ Hardware-specific package additions

### Complete Workflow Tests
- ✅ Prepare → Build workflow
- ✅ Migration + Build
- ✅ Changes shown before building
- ✅ Request hash consistency

### Service Independence Tests
- ✅ Prepare works without build service
- ✅ Services report different capabilities
- ✅ Prepare has no build endpoint

## Environment Variables

Override default URLs:
```bash
export PREPARE_SERVICE_URL=http://prepare-service:8001
export BUILD_SERVICE_URL=http://build-service:8000

pytest tests/test_integration_prepare_build.py -v
```

## Continuous Integration

For CI/CD pipelines, skip integration tests if services aren't running:

```bash
# Only run integration tests if services are available
pytest tests/test_integration_prepare_build.py -v -m integration
```

Tests will automatically skip if services aren't reachable.

## Creating New Test Configs

Create a JSON file in `configs/`:

```json
{
  "url": "http://localhost:8000",
  "prepare_url": "http://localhost:8001",
  "version": "24.10.0",
  "target": "ath79/generic",
  "profile": "my-device",
  "packages": ["luci", "vim"],
  "diff_packages": false,
  "defaults": "...",
  "rootfs_size_mb": 512
}
```

Required fields:
- `url` - Build service URL
- `version` - OpenWrt version
- `target` - Target platform
- `profile` - Device profile

Optional fields:
- `prepare_url` - Prepare service URL (default: http://localhost:8001)
- `packages` - Package list
- `from_version` - Version upgrading from (for migrations)
- `diff_packages` - Absolute vs additional packages
- `defaults` - Default configuration
- `rootfs_size_mb` - Custom rootfs size
- `repositories` - Custom package repositories
- `repository_keys` - Repository signing keys

## Debugging

Enable verbose output:
```bash
python tests/uclient.py tests/configs/basic_build.json --prepare-only 2>&1 | tee debug.log
```

Check service health:
```bash
curl http://localhost:8001/health
curl http://localhost:8000/health
```

View service status:
```bash
curl http://localhost:8001/api/v1/status | jq
```
