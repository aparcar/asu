package models

import "time"

// JobStatus represents the status of a build job
type JobStatus string

const (
	JobStatusPending   JobStatus = "pending"
	JobStatusBuilding  JobStatus = "building"
	JobStatusCompleted JobStatus = "completed"
	JobStatusFailed    JobStatus = "failed"
)

// BuildJob represents a build job in the queue
type BuildJob struct {
	ID            int64      `json:"id" db:"id"`
	RequestHash   string     `json:"request_hash" db:"request_hash"`
	Status        JobStatus  `json:"status" db:"status"`
	StartedAt     *time.Time `json:"started_at,omitempty" db:"started_at"`
	FinishedAt    *time.Time `json:"finished_at,omitempty" db:"finished_at"`
	BuildCmd      string     `json:"build_cmd,omitempty" db:"build_cmd"`
	Manifest      string     `json:"manifest,omitempty" db:"manifest"`
	ErrorMessage  string     `json:"error_message,omitempty" db:"error_message"`
	WorkerID      string     `json:"worker_id,omitempty" db:"worker_id"`
	QueuePosition int        `json:"queue_position,omitempty" db:"queue_position"`
}

// BuildResult represents the result of a completed build
type BuildResult struct {
	RequestHash        string    `json:"request_hash" db:"request_hash"`
	Images             string    `json:"images" db:"images"` // JSON array
	Manifest           string    `json:"manifest" db:"manifest"`
	BuildAt            time.Time `json:"build_at" db:"build_at"`
	CacheHit           bool      `json:"cache_hit" db:"cache_hit"`
	BuildDurationSecs  int       `json:"build_duration_seconds" db:"build_duration_seconds"`
}

// BuildResponse is the API response for build requests
type BuildResponse struct {
	RequestHash    string     `json:"request_hash"`
	Status         JobStatus  `json:"status"`
	QueuePosition  int        `json:"queue_position,omitempty"`
	Images         []string   `json:"images,omitempty"`
	Manifest       string     `json:"manifest,omitempty"`
	ErrorMessage   string     `json:"error_message,omitempty"`
	BuildDuration  int        `json:"build_duration,omitempty"`
	EnqueuedAt     *time.Time `json:"enqueued_at,omitempty"`
	StartedAt      *time.Time `json:"started_at,omitempty"`
	FinishedAt     *time.Time `json:"finished_at,omitempty"`
	CacheHit       bool       `json:"cache_hit,omitempty"`
}
