package models

import "time"

// StatEventType represents different types of statistical events
type StatEventType string

const (
	EventTypeRequest        StatEventType = "request"
	EventTypeCacheHit       StatEventType = "cache_hit"
	EventTypeFailure        StatEventType = "failure"
	EventTypeBuildCompleted StatEventType = "build_completed"
)

// BuildStat represents a statistical event
type BuildStat struct {
	ID            int64         `json:"id" db:"id"`
	Timestamp     time.Time     `json:"timestamp" db:"timestamp"`
	EventType     StatEventType `json:"event_type" db:"event_type"`
	Version       string        `json:"version,omitempty" db:"version"`
	Target        string        `json:"target,omitempty" db:"target"`
	Profile       string        `json:"profile,omitempty" db:"profile"`
	DurationSecs  int           `json:"duration_seconds,omitempty" db:"duration_seconds"`
	DiffPackages  bool          `json:"diff_packages" db:"diff_packages"`
}
