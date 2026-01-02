# ASU Microservices Architecture

This document describes the microservices architecture for ASU (Attended Sysupgrade Server).

## Overview

ASU has been designed to support two deployment models:

1. **Monolithic** - All services in one container (backward compatible)
2. **Microservices** - Independent services in separate containers (new)

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Load Balancer (Nginx)                    │
│                                                                   │
│  /api/v1/build/prepare → Prepare Service                        │
│  /api/v1/build → Build Service                                   │
└─────────────────────────────────────────────────────────────────┘
                           │                    │
        ┌──────────────────┘                    └─────────────────┐
        │                                                          │
        ▼                                                          ▼
┌─────────────────┐                                  ┌─────────────────┐
│ Prepare Service │                                  │  Build Service  │
│  (Lightweight)  │                                  │     (Heavy)     │
├─────────────────┤                                  ├─────────────────┤
│ • Stateless     │                                  │ • Stateful      │
│ • No Redis      │                                  │ • Redis + RQ    │
│ • No Podman     │                                  │ • Podman access │
│ • CPU: 0.5      │                                  │ • CPU: 4+       │
│ • RAM: 512MB    │                                  │ • RAM: 4GB+     │
│ • Fast response │                                  │                 │
└─────────────────┘                                  └─────────────────┘
        │                                                      │
        │                                                      │
        │                                                      ▼
        │                                            ┌─────────────────┐
        │                                            │  Redis Stack    │
        │                                            │  (Queue + Cache)│
        │                                            └─────────────────┘
        │                                                      │
        │                                                      │
        │                                                      ▼
        │                                            ┌─────────────────┐
        │                                            │     Workers     │
        │                                            │  (Podman+IB)    │
        │                                            │   Scalable      │
        │                                            └─────────────────┘
        │
        └─────────────── Shared Libraries ──────────────────────┘
                    (Models, Validation, Package Logic)
```

## Services

### 1. Prepare Service

**Purpose:** Lightweight service for package resolution and request validation.

**Responsibilities:**
- Validate build requests
- Apply package changes/migrations
- Track what packages will be modified
- Return prepared request for user approval
- NO actual building

**Dependencies:**
- `asu.build_request` (BuildRequest model)
- `asu.package_resolution` (PackageResolver)
- `asu.package_changes` (apply_package_changes)
- `asu.util` (validation utilities)
- FastAPI (minimal)

**No Dependencies on:**
- ❌ Redis/RQ
- ❌ Podman
- ❌ ImageBuilder
- ❌ Build infrastructure

**Characteristics:**
- **Stateless**: No persistent state
- **Fast**: Sub-second response times
- **Scalable**: Can run many instances cheaply
- **Independent**: Runs without build infrastructure

**Container:**
- Image: `Containerfile.prepare`
- Port: 8001
- Resources: 0.5 CPU, 512MB RAM

**API Endpoints:**
- `POST /api/v1/build/prepare`

### 2. Build Service

**Purpose:** Heavy service for actual firmware image compilation.

**Responsibilities:**
- Accept build requests (raw or prepared)
- Manage build queue (Redis/RQ)
- Execute builds in Podman containers
- Cache results
- Serve firmware images
- Collect statistics

**Dependencies:**
- `asu.build` (build firmware)
- `asu.build_request` (BuildRequest model)
- `asu.util` (queue management, Redis)
- Redis (queue + cache)
- RQ (job queue)
- Podman (container management)
- ImageBuilder (firmware compilation)

**Characteristics:**
- **Stateful**: Manages queue and cache
- **Resource-Intensive**: Requires significant CPU/RAM
- **Slower**: Build can take minutes
- **Complex**: Many dependencies

**Container:**
- Image: `Containerfile.build`
- Port: 8000
- Resources: 4+ CPU, 4GB+ RAM

**API Endpoints:**
- `POST /api/v1/build`
- `GET /api/v1/build/{hash}`
- `GET /api/v1/stats`
- All other endpoints

### 3. Shared Libraries

Both services share common code but don't share runtime state:

**Shared Modules:**
- `asu/build_request.py` - Request model (Pydantic)
- `asu/package_changes.py` - Package migration logic
- `asu/package_resolution.py` - Resolution algorithm
- `asu/config.py` - Configuration
- `asu/util.py` - Utility functions

**Key Design Principle:**
- Services share **code** (Python modules)
- Services **do not** share **runtime state** (no shared memory, no IPC)
- Communication only via HTTP API or shared database (Redis)

## Deployment Models

### Monolithic Deployment (Default)

```bash
podman-compose up -d
```

All services run in the same container:
- ✅ Simple setup
- ✅ Easier to manage
- ❌ Less scalable
- ❌ Resource inefficient

### Microservices Deployment (Recommended for Production)

```bash
podman-compose -f podman-compose.microservices.yml up -d
```

Services run in separate containers:
- ✅ Independent scaling
- ✅ Better resource utilization
- ✅ Fault isolation
- ✅ Can deploy on different infrastructure
- ❌ More complex setup
- ❌ Requires load balancer

## Scaling Strategies

### Horizontal Scaling

**Prepare Service:**
```bash
podman-compose -f podman-compose.microservices.yml up -d --scale prepare=5
```
- Run 5 prepare instances
- Load balanced by Nginx
- Handle 5x more prepare requests

**Build Workers:**
```bash
podman-compose -f podman-compose.microservices.yml up -d --scale worker=10
```
- Run 10 build workers
- All pull from same Redis queue
- Build 10 images in parallel

### Resource Allocation

Recommended resource allocation per service:

| Service | Instances | CPU/instance | RAM/instance | Total Resources |
|---------|-----------|--------------|--------------|-----------------|
| Prepare | 5 | 0.5 | 512MB | 2.5 CPU, 2.5GB |
| Build   | 1 | 4 | 4GB | 4 CPU, 4GB |
| Workers | 4 | 2 | 2GB | 8 CPU, 8GB |
| Redis   | 1 | 1 | 1GB | 1 CPU, 1GB |
| **Total** | **11** | - | - | **15.5 CPU, 15.5GB** |

Compare to monolithic (all-in-one):
- 1 instance, 8 CPU, 8GB
- Can only handle 1 build + limited prepare requests

## Communication Patterns

### Client → Prepare Service

```
Client → Nginx → Prepare Service → Response
```

1. Client sends prepare request
2. Nginx routes to prepare service
3. Prepare validates and resolves packages
4. Returns prepared request immediately

**Latency:** <1 second

### Client → Build Service (Direct)

```
Client → Nginx → Build Service → Redis → Worker → Response
```

1. Client sends build request
2. Nginx routes to build service
3. Build service enqueues job
4. Worker picks up job
5. Returns job status

**Latency:** Minutes (async)

### Client → Build Service (Prepared)

```
Client → Prepare Service → (approval) → Build Service
```

1. Client calls prepare
2. User reviews changes
3. Client calls build with prepared request
4. Build skips resolution, starts building

**Benefits:**
- User sees changes before building
- Faster build start (no resolution)
- Better UX

## Data Flow

### Request Preparation

```
BuildRequest (raw)
    ↓
PrepareService.prepare()
    ↓
PackageResolver.resolve()
    ↓
apply_package_changes()
    ↓
BuildRequest (prepared) + changes list
```

### Build Execution

```
BuildRequest (raw or prepared)
    ↓
BuildService.build()
    ↓
validate_request() [if not prepared]
    ↓
get_request_hash()
    ↓
check Redis cache
    ↓
enqueue to RQ
    ↓
Worker: build_firmware()
    ↓
Podman: ImageBuilder
    ↓
Store result in Redis + filesystem
```

## Security Considerations

### Prepare Service

- ✅ Minimal attack surface (no Podman, no Redis)
- ✅ Stateless (no persistent data to compromise)
- ✅ Input validation only
- ⚠️ Could be DDoS target (rate limit recommended)

### Build Service

- ✅ Containerized builds (Podman isolation)
- ✅ No new privileges in containers
- ✅ Separate from prepare (blast radius limited)
- ⚠️ Requires Podman socket access
- ⚠️ Resource-intensive (DoS risk)

### Network Isolation

Recommended network topology:
```
Internet
    ↓
Nginx (public)
    ↓
    ├─ Prepare Service (internal network)
    └─ Build Service (internal network)
            ↓
            Redis (internal network, no external access)
            Podman (local socket)
```

## Monitoring & Observability

### Metrics

**Prepare Service:**
- Request rate
- Response time (should be <1s)
- Error rate
- Package changes per request

**Build Service:**
- Queue length
- Build duration
- Success/failure rate
- Cache hit rate
- Resource utilization

### Health Checks

```bash
# Prepare service
curl http://prepare:8001/health

# Build service
curl http://build:8000/health
```

### Logs

Both services log to stdout (container-friendly):
```bash
docker logs asu-prepare
docker logs asu-build
docker logs asu-worker-1
```

## Migration Path

### From Monolithic to Microservices

1. **Deploy microservices alongside monolithic**
   ```bash
   # Keep monolithic running
   podman-compose up -d

   # Start microservices on different ports
   podman-compose -f podman-compose.microservices.yml up -d
   ```

2. **Configure load balancer to route traffic**
   - `/api/v1/build/prepare` → microservices
   - `/api/v1/build` → monolithic (initially)

3. **Test prepare service**
   - Monitor error rates
   - Verify package resolution works

4. **Gradually shift build traffic**
   - Route 10% of builds to microservices
   - Monitor performance
   - Increase to 100%

5. **Decommission monolithic**
   ```bash
   podman-compose down
   ```

## Future Enhancements

### Potential Additional Services

1. **Metadata Service**
   - Handle `/json/v1/*` endpoints
   - Serve version/target/profile data
   - Can be separate from build

2. **Cache Service**
   - Dedicated service for cache management
   - Could use external CDN
   - Reduce build service load

3. **Stats Service**
   - Handle analytics endpoints
   - Time-series database
   - Separate from build queue

### Service Mesh

For very large deployments:
- Istio/Linkerd for service mesh
- Automatic retry/circuit breaking
- Distributed tracing
- mTLS between services

## Troubleshooting

### Prepare Service Issues

**Slow responses:**
- Check if validation data is cached
- Monitor CPU usage
- Scale horizontally

**Validation errors:**
- Check upstream availability
- Verify version data is up-to-date

### Build Service Issues

**Queue backing up:**
- Scale workers horizontally
- Check Podman resource limits
- Monitor ImageBuilder availability

**Cache misses:**
- Verify Redis is running
- Check Redis memory limits
- Review cache TTL settings

## Conclusion

The microservices architecture provides:
- **Flexibility**: Deploy services independently
- **Scalability**: Scale components based on demand
- **Reliability**: Isolate failures
- **Efficiency**: Optimize resource allocation

Choose monolithic for simplicity, microservices for production scale.
