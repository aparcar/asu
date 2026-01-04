-- Build requests table
CREATE TABLE IF NOT EXISTS build_requests (
    request_hash TEXT PRIMARY KEY,
    distro TEXT NOT NULL,
    version TEXT NOT NULL,
    target TEXT NOT NULL,
    profile TEXT NOT NULL,
    packages TEXT, -- JSON array
    packages_versions TEXT, -- JSON object
    defaults TEXT,
    rootfs_size_mb INTEGER,
    repositories TEXT, -- JSON array
    repository_keys TEXT, -- JSON array
    diff_packages BOOLEAN DEFAULT FALSE,
    client TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Build jobs table
CREATE TABLE IF NOT EXISTS build_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- pending, building, completed, failed
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    build_cmd TEXT,
    manifest TEXT, -- JSON
    error_message TEXT,
    worker_id TEXT,
    queue_position INTEGER,
    FOREIGN KEY (request_hash) REFERENCES build_requests(request_hash)
);

CREATE INDEX IF NOT EXISTS idx_build_jobs_request_hash ON build_jobs(request_hash);
CREATE INDEX IF NOT EXISTS idx_build_jobs_status ON build_jobs(status);

-- Build results table
CREATE TABLE IF NOT EXISTS build_results (
    request_hash TEXT PRIMARY KEY,
    images TEXT, -- JSON array of image files
    manifest TEXT, -- JSON manifest
    build_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    cache_hit BOOLEAN DEFAULT FALSE,
    build_duration_seconds INTEGER,
    FOREIGN KEY (request_hash) REFERENCES build_requests(request_hash)
);

-- Statistics table
CREATE TABLE IF NOT EXISTS build_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL, -- request, cache_hit, failure, build_completed
    version TEXT,
    target TEXT,
    profile TEXT,
    duration_seconds INTEGER
);

CREATE INDEX IF NOT EXISTS idx_build_stats_timestamp ON build_stats(timestamp);
CREATE INDEX IF NOT EXISTS idx_build_stats_event_type ON build_stats(event_type);

-- Metadata cache table (for package lists, profiles, etc.)
CREATE TABLE IF NOT EXISTS metadata_cache (
    cache_key TEXT PRIMARY KEY,
    data TEXT, -- JSON data
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_metadata_cache_expires ON metadata_cache(expires_at);

-- Versions and targets cache
CREATE TABLE IF NOT EXISTS versions (
    version TEXT PRIMARY KEY,
    branch TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL,
    target TEXT NOT NULL,
    subtarget TEXT NOT NULL,
    UNIQUE(version, target, subtarget),
    FOREIGN KEY (version) REFERENCES versions(version)
);

CREATE INDEX IF NOT EXISTS idx_targets_version ON targets(version);

-- Profiles cache
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL,
    target TEXT NOT NULL,
    profile TEXT NOT NULL,
    title TEXT,
    data TEXT, -- JSON profile data
    UNIQUE(version, target, profile),
    FOREIGN KEY (version) REFERENCES versions(version)
);

CREATE INDEX IF NOT EXISTS idx_profiles_version_target ON profiles(version, target);
