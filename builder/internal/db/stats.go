package db

import (
	"fmt"
	"time"

	"github.com/aparcar/asu/builder/internal/models"
)

// RecordBuildStat records a statistical event
func (db *DB) RecordBuildStat(stat *models.BuildStat) error {
	query := `
		INSERT INTO build_stats (timestamp, event_type, version, target, profile, duration_seconds, diff_packages)
		VALUES (?, ?, ?, ?, ?, ?, ?)
	`

	_, err := db.Exec(query,
		stat.Timestamp,
		stat.EventType,
		stat.Version,
		stat.Target,
		stat.Profile,
		stat.DurationSecs,
		stat.DiffPackages,
	)

	if err != nil {
		return fmt.Errorf("failed to insert build stat: %w", err)
	}

	return nil
}

// GetBuildStatsPerDay returns build statistics grouped by day
func (db *DB) GetBuildStatsPerDay(days int) (map[string]map[string]int, error) {
	query := `
		SELECT DATE(timestamp) as day, event_type, COUNT(*) as count
		FROM build_stats
		WHERE timestamp >= datetime('now', '-' || ? || ' days')
		GROUP BY day, event_type
		ORDER BY day DESC
	`

	rows, err := db.Query(query, days)
	if err != nil {
		return nil, fmt.Errorf("failed to query build stats: %w", err)
	}
	defer rows.Close()

	stats := make(map[string]map[string]int)
	for rows.Next() {
		var day, eventType string
		var count int

		if err := rows.Scan(&day, &eventType, &count); err != nil {
			return nil, fmt.Errorf("failed to scan stat row: %w", err)
		}

		if stats[day] == nil {
			stats[day] = make(map[string]int)
		}
		stats[day][eventType] = count
	}

	return stats, rows.Err()
}

// GetBuildStatsByVersion returns build statistics grouped by version
func (db *DB) GetBuildStatsByVersion(weeks int) (map[string]map[string]int, error) {
	query := `
		SELECT version, event_type, COUNT(*) as count
		FROM build_stats
		WHERE timestamp >= datetime('now', '-' || ? || ' weeks')
			AND version IS NOT NULL
		GROUP BY version, event_type
		ORDER BY version
	`

	rows, err := db.Query(query, weeks)
	if err != nil {
		return nil, fmt.Errorf("failed to query build stats by version: %w", err)
	}
	defer rows.Close()

	stats := make(map[string]map[string]int)
	for rows.Next() {
		var version, eventType string
		var count int

		if err := rows.Scan(&version, &eventType, &count); err != nil {
			return nil, fmt.Errorf("failed to scan stat row: %w", err)
		}

		if stats[version] == nil {
			stats[version] = make(map[string]int)
		}
		stats[version][eventType] = count
	}

	return stats, rows.Err()
}

// CleanOldStats removes statistics older than the specified number of days
func (db *DB) CleanOldStats(daysToKeep int) error {
	query := `DELETE FROM build_stats WHERE timestamp < datetime('now', '-' || ? || ' days')`
	_, err := db.Exec(query, daysToKeep)
	return err
}

// RecordEvent is a convenience function to record a build event
func (db *DB) RecordEvent(eventType models.StatEventType, version, target, profile string, durationSecs int, diffPackages bool) error {
	stat := &models.BuildStat{
		Timestamp:    time.Now(),
		EventType:    eventType,
		Version:      version,
		Target:       target,
		Profile:      profile,
		DurationSecs: durationSecs,
		DiffPackages: diffPackages,
	}
	return db.RecordBuildStat(stat)
}
