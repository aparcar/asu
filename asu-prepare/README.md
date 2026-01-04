# ASU Prepare Service

Lightweight microservice for OpenWrt firmware build request preparation.

## Purpose

This service handles **package resolution and validation** for OpenWrt firmware build requests. It runs completely independently from the build service and has NO dependencies on:

- ❌ Redis/RQ (no queue management)
- ❌ Podman (no container operations)
- ❌ ImageBuilder (no firmware building)
- ❌ Build infrastructure

## What It Does

✅ Validates build requests
✅ Applies package changes/migrations (e.g., `auc` → `owut`)
✅ Resolves hardware-specific package requirements
✅ Returns prepared package lists for user approval
✅ Tracks all changes made

## API

### POST /api/v1/prepare

Prepare a build request without executing it.

**Request:**
```json
{
  "version": "24.10.0",
  "target": "ath79/generic",
  "profile": "tplink_archer-c7-v5",
  "packages": ["luci", "auc"]
}
```

**Response:**
```json
{
  "status": "prepared",
  "original_packages": ["luci", "auc"],
  "resolved_packages": ["luci", "owut"],
  "changes": [
    {
      "type": "migration",
      "action": "replace",
      "from_package": "auc",
      "to_package": "owut",
      "reason": "Package renamed in 24.10",
      "automatic": true
    }
  ],
  "prepared_request": { ... },
  "request_hash": "abc123..."
}
```

### GET /health

Health check endpoint for load balancers.

## Running

### Development

```bash
cd asu-prepare
poetry install
poetry run uvicorn main:app --reload --port 8001
```

### Production (Docker/Podman)

```bash
podman build -t asu-prepare -f Containerfile .
podman run -p 8001:8001 asu-prepare
```

## Dependencies

Minimal dependencies (no heavy build tools):

- FastAPI - Web framework
- Uvicorn - ASGI server
- Pydantic - Data validation

## Resource Requirements

- **CPU**: 0.5 cores
- **RAM**: 512MB
- **Response Time**: <1 second
- **Scalability**: Horizontal (stateless)

## Architecture

This service is completely stateless and can be scaled horizontally:

```
Load Balancer
      ↓
  ┌───┴───┬───────┬───────┐
  ↓       ↓       ↓       ↓
Prepare Prepare Prepare Prepare
  (1)     (2)     (3)     (4)
```

Each instance can handle requests independently.

## Communication with Build Service

The build service makes HTTP requests to this service:

```python
# In build service
import httpx

async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://prepare-service:8001/api/v1/prepare",
        json=build_request.model_dump()
    )
    prepared = response.json()
```

## Testing

```bash
poetry run pytest
```

## Configuration

Environment variables:

- `UPSTREAM_URL` - OpenWrt downloads URL (default: https://downloads.openwrt.org)
- `MAX_DEFAULTS_LENGTH` - Max first-boot script size (default: 20480)
- `MAX_CUSTOM_ROOTFS_SIZE_MB` - Max custom rootfs size (default: 1024)

## License

Same as ASU main project
