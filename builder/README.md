# ASU Builder (Go)

A high-performance firmware builder service written in Go with SQLite storage.

## Architecture

The Go builder is a single binary that runs both the HTTP API server and background build workers. It replaces the Python implementation with:

- **SQLite Database**: Stores build requests, jobs, results, and statistics
- **Podman Integration**: Uses official Podman Go bindings for container management
- **HTTP API**: RESTful API compatible with existing ASU clients
- **Background Workers**: Concurrent job processing with configurable worker count
- **Package Changes Service**: Calls external service for package modifications

## Components

### Database Layer (`internal/db`)
- SQLite with WAL mode for better concurrency
- Build requests, jobs, results, and statistics
- Automatic migrations on startup

### Builder (`internal/builder`)
- Podman bindings for container management
- ImageBuilder container execution
- Package manifest generation
- Firmware image building

### Queue & Workers (`internal/queue`)
- Job queue management using SQLite
- Configurable worker concurrency
- Automatic retries and error handling
- Build statistics tracking

### HTTP API (`internal/api`)
- RESTful endpoints using Gin framework
- Build request submission
- Build status polling
- Statistics and metrics

## Configuration

Configuration can be provided via environment variables (prefixed with `ASU_`) or YAML config file:

```yaml
# Server settings
server_host: "0.0.0.0"
server_port: 8080

# Database
database_path: "./data/builder.db"

# Storage
public_path: "./public"
store_path: "./public/store"

# Upstream
upstream_url: "https://downloads.openwrt.org"

# Container
container_runtime: "podman"
container_socket_path: "/run/podman/podman.sock"
imagebuilder_registry: "ghcr.io/openwrt/imagebuilder"

# Build settings
max_pending_jobs: 200
job_timeout_seconds: 600
build_ttl_seconds: 86400
failure_ttl_seconds: 3600
allow_defaults: true

# Worker settings
worker_id: "worker-1"
worker_concurrent: 4
worker_poll_seconds: 5

# Package changes service
package_changes_url: "http://localhost:8081"

# Logging
log_level: "info"
```

## Building

```bash
cd builder
go mod download
go build -o asu-builder ./cmd
```

## Running

```bash
# With environment variables
export ASU_DATABASE_PATH="./data/builder.db"
export ASU_SERVER_PORT=8080
export ASU_WORKER_CONCURRENT=4
./asu-builder

# With config file
./asu-builder
```

## API Endpoints

### Build Endpoints

**POST /api/v1/build**
Submit a new build request.

```json
{
  "distro": "openwrt",
  "version": "23.05.0",
  "target": "ath79/generic",
  "profile": "tplink_archer-c7-v5",
  "packages": ["luci", "luci-ssl"],
  "diff_packages": false
}
```

Response (202 Accepted):
```json
{
  "request_hash": "abc123...",
  "status": "pending",
  "queue_position": 3
}
```

**GET /api/v1/build/:request_hash**
Check build status.

Response (200 OK when completed):
```json
{
  "request_hash": "abc123...",
  "status": "completed",
  "images": ["openwrt-...-sysupgrade.bin"],
  "manifest": "...",
  "build_duration": 120,
  "finished_at": "2024-01-01T12:00:00Z"
}
```

### Statistics Endpoints

**GET /api/v1/stats**
Get current queue statistics.

**GET /api/v1/builds-per-day?days=30**
Get build statistics grouped by day.

**GET /api/v1/builds-by-version?weeks=26**
Get build statistics grouped by version.

**GET /api/v1/diff-packages-stats?days=30**
Get statistics about diff_packages option usage.

Response:
```json
{
  "total_builds": 1000,
  "diff_packages_true": 750,
  "diff_packages_false": 250,
  "percentage_true": 75.0,
  "percentage_false": 25.0
}
```

**GET /api/v1/diff-packages-by-version?weeks=26**
Get diff_packages statistics grouped by version.

Response:
```json
[
  {
    "version": "23.05.0",
    "total_builds": 500,
    "diff_packages_true": 400,
    "diff_packages_false": 100,
    "percentage_true": 80.0
  }
]
```

**GET /api/v1/diff-packages-trend?days=30**
Get daily trend of diff_packages usage.

Response:
```json
[
  {
    "date": "2024-01-01",
    "diff_packages_true": 50,
    "diff_packages_false": 10,
    "total": 60
  }
]
```

## Database Schema

See `migrations/001_initial_schema.sql` for the complete schema.

Key tables:
- `build_requests`: Build request details
- `build_jobs`: Job queue and status
- `build_results`: Completed build results
- `build_stats`: Statistical events
- `metadata_cache`: Cached package metadata

## Package Changes Service

The builder calls an external package changes service to apply version-specific package modifications. The service should implement:

**POST /apply**
```json
{
  "version": "23.05.0",
  "target": "ath79/generic",
  "profile": "tplink_archer-c7-v5",
  "packages": ["luci"],
  "default_packages": ["base-files", "busybox", ...],
  "diff_packages": false
}
```

Response:
```json
{
  "packages": ["luci", "additional-package", ...]
}
```

If the service is unavailable, the builder falls back to using the original package list.

## Migration from Python

The Go builder is designed to be a drop-in replacement for the Python implementation:

1. Same API endpoints and request/response formats
2. Compatible with existing clients
3. Stores builds in the same directory structure
4. Can coexist with Python service during migration

### Migration Steps

1. Set up Go builder with same `public_path` as Python service
2. Start Go builder on different port
3. Gradually migrate clients to new endpoint
4. Shut down Python service when migration is complete

## Performance

Benefits over Python implementation:

- **Lower memory usage**: Go's efficient memory management
- **Better concurrency**: Native goroutines vs Python threading
- **Faster startup**: No interpreter overhead
- **SQLite with WAL**: Better concurrent read/write performance
- **Native Podman bindings**: More efficient than subprocess calls

## Development

### Project Structure

```
builder/
├── cmd/
│   └── main.go              # Application entry point
├── internal/
│   ├── api/                 # HTTP API handlers
│   ├── builder/             # Build logic
│   ├── config/              # Configuration
│   ├── container/           # Podman integration
│   ├── db/                  # Database layer
│   ├── models/              # Data models
│   ├── queue/               # Job queue & workers
│   └── stats/               # Statistics
├── migrations/              # Database migrations
├── go.mod
├── go.sum
└── README.md
```

### Running Tests

```bash
go test ./...
```

### Building for Production

```bash
CGO_ENABLED=1 go build -ldflags="-s -w" -o asu-builder ./cmd
```

## License

Same as main ASU project.
