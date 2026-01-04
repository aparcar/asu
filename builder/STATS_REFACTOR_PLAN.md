# Statistics System Refactor Plan

## Current State Analysis

### Existing System
The current statistics system uses a single `build_stats` table that tracks:
- Event types (request, cache_hit, failure, build_completed)
- Version, target, profile (optional)
- Build duration (for completed builds)
- Diff packages flag
- Timestamp

### Limitations
1. **Event-based design**: Relies on event_type strings, making complex queries harder
2. **Missing client tracking**: No way to see which clients are using the service
3. **No request metadata**: Can't track request patterns or sizes
4. **Limited failure analysis**: No detailed error categorization
5. **No resource metrics**: Can't track build resource usage
6. **Denormalized data**: Version/target/profile duplicated across events

## Proposed Architecture

### Design Principles
1. **Separation of concerns**: Different tables for different stat types
2. **Relational integrity**: Link stats to build_requests for referential data
3. **Time-series optimized**: Efficient querying by time ranges
4. **Aggregation-friendly**: Pre-computed aggregates where beneficial
5. **Client analytics**: Track client usage patterns
6. **Performance monitoring**: Track build performance metrics

### New Database Schema

```sql
-- Build execution metrics (one per build attempt)
CREATE TABLE build_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_hash TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    duration_seconds INTEGER,
    status TEXT NOT NULL, -- success, failure, timeout, cancelled
    error_category TEXT, -- validation, container, build, storage, network
    error_message TEXT,
    cache_hit BOOLEAN DEFAULT FALSE,
    worker_id TEXT,
    FOREIGN KEY (request_hash) REFERENCES build_requests(request_hash)
);

-- Request metadata (one per unique request)
CREATE TABLE request_metadata (
    request_hash TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    target TEXT NOT NULL,
    profile TEXT NOT NULL,
    diff_packages BOOLEAN NOT NULL,
    package_count INTEGER,
    has_custom_repos BOOLEAN,
    has_defaults BOOLEAN,
    rootfs_size_mb INTEGER,
    first_requested_at TIMESTAMP NOT NULL,
    last_requested_at TIMESTAMP NOT NULL,
    total_requests INTEGER DEFAULT 1,
    cache_hits INTEGER DEFAULT 0,
    successful_builds INTEGER DEFAULT 0,
    failed_builds INTEGER DEFAULT 0,
    FOREIGN KEY (request_hash) REFERENCES build_requests(request_hash)
);

-- Client usage tracking
CREATE TABLE client_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    request_hash TEXT NOT NULL,
    cache_hit BOOLEAN DEFAULT FALSE,
    status TEXT, -- queued, building, success, failure
    FOREIGN KEY (request_hash) REFERENCES build_requests(request_hash)
);

-- Daily aggregates (pre-computed for performance)
CREATE TABLE stats_daily (
    date DATE PRIMARY KEY,
    total_requests INTEGER DEFAULT 0,
    unique_requests INTEGER DEFAULT 0,
    cache_hits INTEGER DEFAULT 0,
    successful_builds INTEGER DEFAULT 0,
    failed_builds INTEGER DEFAULT 0,
    avg_build_duration_seconds REAL,
    max_build_duration_seconds INTEGER,
    min_build_duration_seconds INTEGER,
    total_build_time_seconds INTEGER,
    unique_clients INTEGER DEFAULT 0,
    diff_packages_true INTEGER DEFAULT 0,
    diff_packages_false INTEGER DEFAULT 0
);

-- Version/target popularity (pre-computed)
CREATE TABLE stats_version_target (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL,
    target TEXT NOT NULL,
    date DATE NOT NULL,
    request_count INTEGER DEFAULT 0,
    unique_profiles INTEGER DEFAULT 0,
    cache_hit_rate REAL,
    avg_build_duration REAL,
    UNIQUE(version, target, date)
);

-- Profile popularity
CREATE TABLE stats_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL,
    target TEXT NOT NULL,
    profile TEXT NOT NULL,
    date DATE NOT NULL,
    request_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    avg_build_duration REAL,
    UNIQUE(version, target, profile, date)
);

-- Error analytics
CREATE TABLE error_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_category TEXT NOT NULL,
    error_type TEXT,
    version TEXT,
    target TEXT,
    request_hash TEXT,
    count INTEGER DEFAULT 1
);

-- Indices for performance
CREATE INDEX idx_build_metrics_started ON build_metrics(started_at);
CREATE INDEX idx_build_metrics_status ON build_metrics(status);
CREATE INDEX idx_build_metrics_request ON build_metrics(request_hash);
CREATE INDEX idx_client_stats_client ON client_stats(client);
CREATE INDEX idx_client_stats_timestamp ON client_stats(timestamp);
CREATE INDEX idx_request_metadata_version ON request_metadata(version);
CREATE INDEX idx_request_metadata_target ON request_metadata(target);
CREATE INDEX idx_request_metadata_diff ON request_metadata(diff_packages);
CREATE INDEX idx_error_stats_category ON error_stats(error_category);
CREATE INDEX idx_error_stats_timestamp ON error_stats(timestamp);
```

## Data Collection Points

### 1. Request Receipt (POST /api/v1/build)
```go
// Record in request_metadata
- Update or create request metadata entry
- Increment total_requests counter
- Update last_requested_at

// Record in client_stats
- Log client identifier
- Record request_hash
- Status: "queued"
```

### 2. Cache Hit
```go
// Update request_metadata
- Increment cache_hits counter

// Update client_stats
- Set cache_hit = true
- Status: "success"
```

### 3. Build Start
```go
// Create build_metrics entry
- Record started_at
- Set status = "building"
- Record worker_id
```

### 4. Build Complete (Success)
```go
// Update build_metrics
- Record finished_at
- Calculate duration_seconds
- Set status = "success"

// Update request_metadata
- Increment successful_builds

// Update client_stats
- Set status = "success"
```

### 5. Build Failure
```go
// Update build_metrics
- Record finished_at
- Set status = "failure"
- Categorize error (validation/container/build/etc)
- Record error_message

// Update request_metadata
- Increment failed_builds

// Update client_stats
- Set status = "failure"

// Record in error_stats
- Log error category and type
- Record version/target for analysis
```

### 6. Daily Aggregation (Cron Job)
```go
// Run at midnight or periodically
- Aggregate build_metrics into stats_daily
- Update stats_version_target
- Update stats_profiles
- Clean up old detailed records if needed
```

## New API Endpoints

### Overview Endpoints

**GET /api/v1/stats/overview?days=7**
```json
{
  "period": {
    "start": "2024-01-01",
    "end": "2024-01-07",
    "days": 7
  },
  "totals": {
    "requests": 10000,
    "unique_requests": 2500,
    "cache_hits": 5000,
    "cache_hit_rate": 50.0,
    "successful_builds": 4500,
    "failed_builds": 500,
    "success_rate": 90.0
  },
  "build_performance": {
    "avg_duration_seconds": 120,
    "median_duration_seconds": 110,
    "p95_duration_seconds": 250,
    "total_build_time_hours": 150
  },
  "clients": {
    "total_unique": 50,
    "top_5": [
      {"client": "asu-web", "requests": 3000},
      {"client": "luci", "requests": 2000}
    ]
  },
  "diff_packages": {
    "enabled": 7500,
    "disabled": 2500,
    "percentage_enabled": 75.0
  }
}
```

### Version/Target Analytics

**GET /api/v1/stats/versions?days=30**
```json
[
  {
    "version": "23.05.0",
    "requests": 5000,
    "unique_targets": 25,
    "cache_hit_rate": 45.0,
    "avg_build_duration": 125,
    "success_rate": 92.0,
    "top_targets": [
      {"target": "ath79/generic", "requests": 1500},
      {"target": "ramips/mt7621", "requests": 1200}
    ]
  }
]
```

**GET /api/v1/stats/targets?version=23.05.0&days=30**
```json
[
  {
    "target": "ath79/generic",
    "requests": 1500,
    "unique_profiles": 50,
    "cache_hit_rate": 50.0,
    "avg_build_duration": 115,
    "top_profiles": [
      {"profile": "tplink_archer-c7-v5", "requests": 300},
      {"profile": "tplink_archer-c7-v2", "requests": 250}
    ]
  }
]
```

### Profile Analytics

**GET /api/v1/stats/profiles?version=23.05.0&target=ath79/generic&days=30**
```json
[
  {
    "profile": "tplink_archer-c7-v5",
    "requests": 300,
    "successful_builds": 280,
    "failed_builds": 20,
    "success_rate": 93.3,
    "avg_build_duration": 120,
    "cache_hit_rate": 40.0
  }
]
```

### Client Analytics

**GET /api/v1/stats/clients?days=30**
```json
[
  {
    "client": "asu-web",
    "total_requests": 3000,
    "unique_builds": 800,
    "cache_hits": 2200,
    "cache_hit_rate": 73.3,
    "successful_builds": 750,
    "failed_builds": 50,
    "success_rate": 93.75,
    "top_versions": [
      {"version": "23.05.0", "requests": 2000},
      {"version": "22.03.5", "requests": 1000}
    ]
  }
]
```

**GET /api/v1/stats/clients/:client?days=30**
Detailed breakdown for a specific client.

### Diff Packages Analytics

**GET /api/v1/stats/diff-packages?days=30**
```json
{
  "overview": {
    "total_builds": 10000,
    "diff_packages_enabled": 7500,
    "diff_packages_disabled": 2500,
    "percentage_enabled": 75.0
  },
  "by_version": [
    {
      "version": "23.05.0",
      "total": 5000,
      "enabled": 4000,
      "disabled": 1000,
      "percentage_enabled": 80.0
    }
  ],
  "trend": [
    {
      "date": "2024-01-01",
      "enabled": 250,
      "disabled": 50,
      "percentage_enabled": 83.3
    }
  ]
}
```

### Error Analytics

**GET /api/v1/stats/errors?days=7**
```json
{
  "total_errors": 500,
  "by_category": [
    {
      "category": "build",
      "count": 300,
      "percentage": 60.0,
      "top_errors": [
        {
          "type": "package_not_found",
          "count": 150,
          "affected_versions": ["23.05.0", "22.03.5"]
        }
      ]
    },
    {
      "category": "container",
      "count": 150,
      "percentage": 30.0
    }
  ],
  "by_version": [
    {"version": "23.05.0", "errors": 200},
    {"version": "22.03.5", "errors": 150}
  ]
}
```

### Performance Analytics

**GET /api/v1/stats/performance?days=30**
```json
{
  "build_duration": {
    "avg_seconds": 120,
    "median_seconds": 110,
    "p50_seconds": 110,
    "p90_seconds": 200,
    "p95_seconds": 250,
    "p99_seconds": 400,
    "min_seconds": 45,
    "max_seconds": 600
  },
  "by_version": [
    {
      "version": "23.05.0",
      "avg_duration": 115,
      "median_duration": 105
    }
  ],
  "slowest_builds": [
    {
      "request_hash": "abc123",
      "version": "23.05.0",
      "target": "x86/64",
      "duration": 580,
      "package_count": 250
    }
  ]
}
```

### Time Series Data

**GET /api/v1/stats/timeseries?days=30&interval=day**
```json
[
  {
    "timestamp": "2024-01-01",
    "requests": 400,
    "cache_hits": 200,
    "successful_builds": 180,
    "failed_builds": 20,
    "avg_build_duration": 125,
    "unique_clients": 15
  }
]
```

## Implementation Strategy

### Phase 1: Database Migration
1. Create new tables alongside existing `build_stats`
2. Add migration script to populate historical data
3. Implement backward compatibility

### Phase 2: Data Collection
1. Update API handlers to record to new tables
2. Update worker to record build metrics
3. Keep writing to old `build_stats` for compatibility

### Phase 3: Aggregation System
1. Implement daily aggregation job
2. Create hourly rollup for recent data
3. Add cleanup for old detailed records

### Phase 4: API Endpoints
1. Implement new statistics endpoints
2. Add filtering and pagination
3. Optimize queries with indices

### Phase 5: Deprecation
1. Mark old endpoints as deprecated
2. Provide migration guide
3. Eventually remove old `build_stats` table

## Performance Considerations

### Indexing Strategy
- Index on timestamp for time-range queries
- Composite indices on (version, target) for common queries
- Index on client for client analytics

### Aggregation
- Pre-compute daily statistics
- Use materialized views or scheduled jobs
- Cache frequently accessed data

### Data Retention
- Keep detailed `build_metrics` for 90 days
- Keep `client_stats` for 180 days
- Keep aggregated `stats_daily` indefinitely
- Archive old data to separate tables

### Query Optimization
- Use prepared statements
- Implement connection pooling
- Add query result caching
- Batch inserts where possible

## Data Models (Go)

```go
// BuildMetric represents a single build execution
type BuildMetric struct {
    ID              int64     `json:"id"`
    RequestHash     string    `json:"request_hash"`
    StartedAt       time.Time `json:"started_at"`
    FinishedAt      *time.Time `json:"finished_at,omitempty"`
    DurationSeconds int       `json:"duration_seconds,omitempty"`
    Status          string    `json:"status"` // success, failure, timeout
    ErrorCategory   string    `json:"error_category,omitempty"`
    ErrorMessage    string    `json:"error_message,omitempty"`
    CacheHit        bool      `json:"cache_hit"`
    WorkerID        string    `json:"worker_id,omitempty"`
}

// RequestMetadata aggregates data about a unique build request
type RequestMetadata struct {
    RequestHash       string    `json:"request_hash"`
    Version           string    `json:"version"`
    Target            string    `json:"target"`
    Profile           string    `json:"profile"`
    DiffPackages      bool      `json:"diff_packages"`
    PackageCount      int       `json:"package_count"`
    HasCustomRepos    bool      `json:"has_custom_repos"`
    HasDefaults       bool      `json:"has_defaults"`
    RootfsSizeMB      int       `json:"rootfs_size_mb"`
    FirstRequestedAt  time.Time `json:"first_requested_at"`
    LastRequestedAt   time.Time `json:"last_requested_at"`
    TotalRequests     int       `json:"total_requests"`
    CacheHits         int       `json:"cache_hits"`
    SuccessfulBuilds  int       `json:"successful_builds"`
    FailedBuilds      int       `json:"failed_builds"`
}

// ClientStat tracks individual client activity
type ClientStat struct {
    ID          int64     `json:"id"`
    Client      string    `json:"client"`
    Timestamp   time.Time `json:"timestamp"`
    RequestHash string    `json:"request_hash"`
    CacheHit    bool      `json:"cache_hit"`
    Status      string    `json:"status"`
}

// DailyStat represents pre-computed daily statistics
type DailyStat struct {
    Date                    string  `json:"date"`
    TotalRequests           int     `json:"total_requests"`
    UniqueRequests          int     `json:"unique_requests"`
    CacheHits               int     `json:"cache_hits"`
    SuccessfulBuilds        int     `json:"successful_builds"`
    FailedBuilds            int     `json:"failed_builds"`
    AvgBuildDurationSeconds float64 `json:"avg_build_duration_seconds"`
    MaxBuildDurationSeconds int     `json:"max_build_duration_seconds"`
    MinBuildDurationSeconds int     `json:"min_build_duration_seconds"`
    TotalBuildTimeSeconds   int     `json:"total_build_time_seconds"`
    UniqueClients           int     `json:"unique_clients"`
    DiffPackagesTrue        int     `json:"diff_packages_true"`
    DiffPackagesFalse       int     `json:"diff_packages_false"`
}

// StatsOverview provides high-level statistics
type StatsOverview struct {
    Period           PeriodInfo           `json:"period"`
    Totals           TotalStats           `json:"totals"`
    BuildPerformance BuildPerformanceStats `json:"build_performance"`
    Clients          ClientOverviewStats   `json:"clients"`
    DiffPackages     DiffPackagesOverview  `json:"diff_packages"`
}
```

## Migration Path

### Backward Compatibility
- Keep existing `/api/v1/builds-per-day` endpoint
- Keep existing `/api/v1/builds-by-version` endpoint
- Keep existing `/api/v1/diff-packages-*` endpoints
- Add deprecation warnings in responses

### Data Migration Script
```sql
-- Migrate existing build_stats to new tables
INSERT INTO build_metrics (request_hash, started_at, finished_at, duration_seconds, status, cache_hit)
SELECT
    br.request_hash,
    bs.timestamp,
    bs.timestamp + (bs.duration_seconds || ' seconds')::interval,
    bs.duration_seconds,
    CASE bs.event_type
        WHEN 'build_completed' THEN 'success'
        WHEN 'failure' THEN 'failure'
        ELSE 'unknown'
    END,
    bs.event_type = 'cache_hit'
FROM build_stats bs
JOIN build_requests br ON bs.version = br.version
    AND bs.target = br.target
    AND bs.profile = br.profile
WHERE bs.event_type IN ('build_completed', 'failure', 'cache_hit');

-- Populate request_metadata from build_requests
INSERT INTO request_metadata (...)
SELECT ... FROM build_requests;
```

## Monitoring & Alerts

### Key Metrics to Monitor
1. Build success rate trending down
2. Average build duration increasing
3. High failure rate for specific version/target
4. Client error rates
5. Cache hit rate dropping
6. Queue length growing

### Alert Thresholds
- Success rate < 85%
- Average build duration > 300s
- Cache hit rate < 30%
- Any client with > 50% error rate
- Queue length > 100 for > 1 hour

## Benefits of Refactor

### Current Pain Points Solved
✅ **Better client tracking** - Know which clients are heavy users
✅ **Detailed failure analysis** - Categorize and track error types
✅ **Performance insights** - Identify slow builds and optimization opportunities
✅ **Request pattern analysis** - Understand what's being built
✅ **Cache effectiveness** - Measure and improve cache hit rates
✅ **Version adoption** - Track which versions are popular
✅ **Resource planning** - Predict capacity needs based on trends

### Query Performance
- Pre-aggregated data = fast dashboard loads
- Indexed queries = sub-second response times
- Time-series optimized = efficient trend analysis

### Operational Benefits
- Better capacity planning
- Identify problematic builds
- Track API usage patterns
- Monitor service health
- Make data-driven decisions

## Next Steps

1. Review and approve this plan
2. Create database migration (phase 1)
3. Implement data collection (phase 2)
4. Build aggregation system (phase 3)
5. Create new API endpoints (phase 4)
6. Deprecate old system (phase 5)

## Open Questions

1. **Data retention**: How long should we keep detailed metrics?
2. **Aggregation frequency**: Hourly, daily, or both?
3. **API rate limiting**: Should stats endpoints have different limits?
4. **Export formats**: Should we support CSV/JSON export?
5. **Real-time updates**: WebSocket for live statistics?
6. **Dashboard**: Should we build a visualization UI?
