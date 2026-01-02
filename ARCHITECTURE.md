# ASU Microservices Architecture

## Overview

ASU uses a true microservices architecture where services are **completely independent** with **NO shared code**. Services communicate only via HTTP.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Load Balancer                          │
│  /api/v1/build/prepare → asu-prepare:8001               │
│  /api/v1/build →         asu:8000                        │
└──────────────────────────────────────────────────────────┘
            │                              │
            ▼                              ▼
   ┌────────────────┐           ┌────────────────┐
   │ asu-prepare/   │◄──HTTP────│ asu/           │
   │ (Separate repo)│           │ (Main repo)    │
   ├────────────────┤           ├────────────────┤
   │ • FastAPI      │           │ • FastAPI      │
   │ • Pydantic     │           │ • Redis/RQ     │
   │ • Package      │           │ • Podman       │
   │   resolution   │           │ • ImageBuilder │
   │ • 512MB RAM    │           │ • 4GB+ RAM     │
   │ • 0.5 CPU      │           │ • 4+ CPU       │
   └────────────────┘           └────────────────┘
                                        │
                                        ├─ Redis
                                        └─ Workers (scalable)
```

## Services

### 1. Prepare Service (`asu-prepare/`)

**Purpose:** Lightweight package resolution and validation.

**Location:** `asu-prepare/` directory (separate codebase)

**Files:**
- `main.py` - FastAPI app
- `build_request.py` - Data models
- `package_changes.py` - Migration logic
- `package_resolution.py` - Resolution algorithm
- `config.py` - Minimal config
- `Containerfile` - Container definition

**Dependencies:**
- FastAPI, Uvicorn, Pydantic
- NO Redis, NO Podman, NO build tools

**API:**
- `POST /api/v1/prepare` - Resolve packages

**Communication:**
- **Receives:** HTTP requests from clients or build service
- **Returns:** JSON with resolved packages

**Resources:**
- CPU: 0.5 cores
- RAM: 512MB
- Response time: <1s

### 2. Build Service (`asu/`)

**Purpose:** Heavy firmware building service.

**Location:** `asu/` directory (main codebase)

**Dependencies:**
- Everything from original ASU
- **PLUS** httpx for calling prepare service

**Communication:**
- **Calls:** Prepare service via HTTP for package resolution
- **Uses:** Redis for queue/cache
- **Uses:** Podman for builds

**Modified Files:**
- `asu/routers/api.py` - Proxies prepare requests via HTTP
- `asu/config.py` - Added `prepare_service_url` setting

## Communication Flow

### Prepare Request

```
Client
  ↓ POST /api/v1/build/prepare
Build Service (asu/)
  ↓ HTTP POST /api/v1/prepare
Prepare Service (asu-prepare/)
  ↓ Package resolution
Build Service
  ↓ Add cache info
Client
```

### Build Request (Direct)

```
Client
  ↓ POST /api/v1/build
Build Service
  ↓ Apply package changes locally
  ↓ Queue build job
Workers
  ↓ Build firmware
Client
```

### Build Request (Prepared)

```
Client
  ↓ POST /api/v1/build/prepare
Prepare Service
  ↓ Return resolved packages
Client (user approval)
  ↓ POST /api/v1/build?skip_package_resolution=true
Build Service
  ↓ Queue build (no package changes)
Workers
  ↓ Build firmware
Client
```

## Key Design Principles

### 1. No Shared Code

- Each service has its OWN copy of necessary files
- NO `from asu.X import Y` between services
- Communication ONLY via HTTP

**Benefits:**
- Can deploy/version independently
- No dependency conflicts
- Clear service boundaries
- Could rewrite in different language

### 2. HTTP-Only Communication

Services communicate via HTTP, not Python imports:

```python
# Build service calling prepare service
async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://asu-prepare:8001/api/v1/prepare",
        json=build_request.model_dump()
    )
```

### 3. Independent Deployment

Each service can be deployed separately:

```bash
# Deploy only prepare service
cd asu-prepare
podman build -t asu-prepare .
podman run -p 8001:8001 asu-prepare

# Deploy only build service
cd ..
podman build -t asu-build .
podman run -p 8000:8000 asu-build
```

## Deployment

### Microservices (Recommended)

```bash
podman-compose -f podman-compose.microservices.yml up -d
```

**Services Started:**
- `asu-prepare` - Prepare service (port 8001)
- `asu-build` - Build service (port 8000)
- `asu-worker` - Build workers (scalable)
- `redis` - Queue and cache
- `nginx` - Load balancer (optional)

### Monolithic (Backward Compatible)

```bash
podman-compose up -d
```

All functionality in one container (original behavior).

## Scaling

### Horizontal Scaling

```bash
# Scale prepare service (cheap, lightweight)
podman-compose -f podman-compose.microservices.yml up -d --scale prepare=5

# Scale build workers (expensive, heavy)
podman-compose -f podman-compose.microservices.yml up -d --scale worker=10
```

### Resource Allocation

| Service | Instances | CPU/each | RAM/each | Total |
|---------|-----------|----------|----------|-------|
| Prepare | 5 | 0.5 | 512MB | 2.5 CPU, 2.5GB |
| Build | 1 | 4 | 4GB | 4 CPU, 4GB |
| Workers | 4 | 2 | 2GB | 8 CPU, 8GB |
| Redis | 1 | 1 | 1GB | 1 CPU, 1GB |
| **Total** | **11** | - | - | **15.5 CPU, 15.5GB** |

## Configuration

### Environment Variables

**Prepare Service:**
- `UPSTREAM_URL` - OpenWrt downloads URL

**Build Service:**
- `PREPARE_SERVICE_URL` - Prepare service URL (default: `http://asu-prepare:8001`)
- `REDIS_URL` - Redis connection string
- All existing ASU variables

### Service Discovery

Build service finds prepare service via:
1. Environment variable `PREPARE_SERVICE_URL`
2. Default: `http://asu-prepare:8001` (container name)

## Migration Path

### From Monolithic

1. Deploy microservices alongside monolithic
2. Route prepare requests to new service
3. Monitor and test
4. Gradually shift build requests
5. Decommission monolithic

### Code Duplication

Yes, there is code duplication (BuildRequest model, package logic). This is **intentional**:

- **Pros:** Complete independence, separate versioning, no coupling
- **Cons:** Updates must be made to both services

**Philosophy:** Prefer duplication over coupling for microservices.

## Benefits

✅ **True Independence:** Services can be developed separately
✅ **Technology Freedom:** Could rewrite prepare in Go, Rust, etc.
✅ **Easy Scaling:** Scale services independently based on load
✅ **Clear Boundaries:** HTTP API is the contract
✅ **Fault Isolation:** Prepare failure doesn't affect builds
✅ **Resource Efficiency:** Run many cheap prepare instances

## Drawbacks

❌ **Code Duplication:** Models and logic duplicated
❌ **Network Overhead:** HTTP calls vs. function calls
❌ **Complexity:** More moving parts
❌ **Consistency:** Updates must be synchronized

## When to Use

**Use Microservices When:**
- High traffic (>1000 prepares/day)
- Need independent scaling
- Different teams own services
- Want deployment flexibility

**Use Monolithic When:**
- Small deployment (<100 builds/day)
- Single admin
- Simplicity preferred
- Limited resources

## Testing

### Prepare Service

```bash
cd asu-prepare
poetry run pytest
```

### Build Service

```bash
cd ..
poetry run pytest
```

### Integration Testing

```bash
# Start both services
podman-compose -f podman-compose.microservices.yml up -d

# Test prepare
curl -X POST http://localhost:8001/api/v1/prepare \
  -H "Content-Type: application/json" \
  -d '{"version":"24.10.0","target":"ath79/generic","profile":"test","packages":["luci","auc"]}'

# Test build calling prepare
curl -X POST http://localhost:8000/api/v1/build/prepare \
  -H "Content-Type: application/json" \
  -d '{"version":"24.10.0","target":"ath79/generic","profile":"test","packages":["luci"]}'
```

## Monitoring

### Health Checks

```bash
# Prepare service
curl http://asu-prepare:8001/health

# Build service
curl http://asu-build:8000/health
```

### Metrics

Each service exposes metrics independently:
- Request count
- Response time
- Error rate
- Resource usage

## Future Enhancements

1. **Service Mesh:** Istio/Linkerd for advanced routing
2. **gRPC:** Replace HTTP JSON with gRPC for performance
3. **Event Bus:** Redis Streams or RabbitMQ for async communication
4. **API Gateway:** Kong or similar for centralized routing
5. **Separate Languages:** Rewrite prepare in Go for performance

## Summary

ASU uses true microservices with complete code separation. Services communicate only via HTTP, enabling independent development, deployment, and scaling.
