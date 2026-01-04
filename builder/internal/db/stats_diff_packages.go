package db

import (
	"fmt"
)

// DiffPackagesStats represents statistics about diff_packages usage
type DiffPackagesStats struct {
	TotalBuilds       int `json:"total_builds"`
	DiffPackagesTrue  int `json:"diff_packages_true"`
	DiffPackagesFalse int `json:"diff_packages_false"`
	PercentageTrue    float64 `json:"percentage_true"`
	PercentageFalse   float64 `json:"percentage_false"`
}

// GetDiffPackagesStats returns statistics about diff_packages usage
func (db *DB) GetDiffPackagesStats(days int) (*DiffPackagesStats, error) {
	query := `
		SELECT
			COUNT(*) as total,
			SUM(CASE WHEN diff_packages = 1 THEN 1 ELSE 0 END) as diff_true,
			SUM(CASE WHEN diff_packages = 0 THEN 1 ELSE 0 END) as diff_false
		FROM build_stats
		WHERE timestamp >= datetime('now', '-' || ? || ' days')
			AND event_type IN ('request', 'build_completed')
	`

	var total, diffTrue, diffFalse int
	err := db.QueryRow(query, days).Scan(&total, &diffTrue, &diffFalse)
	if err != nil {
		return nil, fmt.Errorf("failed to query diff_packages stats: %w", err)
	}

	stats := &DiffPackagesStats{
		TotalBuilds:       total,
		DiffPackagesTrue:  diffTrue,
		DiffPackagesFalse: diffFalse,
	}

	if total > 0 {
		stats.PercentageTrue = float64(diffTrue) / float64(total) * 100
		stats.PercentageFalse = float64(diffFalse) / float64(total) * 100
	}

	return stats, nil
}

// DiffPackagesByVersion represents diff_packages stats grouped by version
type DiffPackagesByVersion struct {
	Version           string  `json:"version"`
	TotalBuilds       int     `json:"total_builds"`
	DiffPackagesTrue  int     `json:"diff_packages_true"`
	DiffPackagesFalse int     `json:"diff_packages_false"`
	PercentageTrue    float64 `json:"percentage_true"`
}

// GetDiffPackagesStatsByVersion returns diff_packages statistics grouped by version
func (db *DB) GetDiffPackagesStatsByVersion(weeks int) ([]*DiffPackagesByVersion, error) {
	query := `
		SELECT
			version,
			COUNT(*) as total,
			SUM(CASE WHEN diff_packages = 1 THEN 1 ELSE 0 END) as diff_true,
			SUM(CASE WHEN diff_packages = 0 THEN 1 ELSE 0 END) as diff_false
		FROM build_stats
		WHERE timestamp >= datetime('now', '-' || ? || ' weeks')
			AND version IS NOT NULL
			AND event_type IN ('request', 'build_completed')
		GROUP BY version
		ORDER BY version DESC
	`

	rows, err := db.Query(query, weeks)
	if err != nil {
		return nil, fmt.Errorf("failed to query diff_packages stats by version: %w", err)
	}
	defer rows.Close()

	var stats []*DiffPackagesByVersion
	for rows.Next() {
		var version string
		var total, diffTrue, diffFalse int

		if err := rows.Scan(&version, &total, &diffTrue, &diffFalse); err != nil {
			return nil, fmt.Errorf("failed to scan row: %w", err)
		}

		stat := &DiffPackagesByVersion{
			Version:           version,
			TotalBuilds:       total,
			DiffPackagesTrue:  diffTrue,
			DiffPackagesFalse: diffFalse,
		}

		if total > 0 {
			stat.PercentageTrue = float64(diffTrue) / float64(total) * 100
		}

		stats = append(stats, stat)
	}

	return stats, rows.Err()
}

// DiffPackagesTrend represents diff_packages usage over time
type DiffPackagesTrend struct {
	Date              string `json:"date"`
	DiffPackagesTrue  int    `json:"diff_packages_true"`
	DiffPackagesFalse int    `json:"diff_packages_false"`
	Total             int    `json:"total"`
}

// GetDiffPackagesTrend returns diff_packages usage trend over time
func (db *DB) GetDiffPackagesTrend(days int) ([]*DiffPackagesTrend, error) {
	query := `
		SELECT
			DATE(timestamp) as day,
			SUM(CASE WHEN diff_packages = 1 THEN 1 ELSE 0 END) as diff_true,
			SUM(CASE WHEN diff_packages = 0 THEN 1 ELSE 0 END) as diff_false,
			COUNT(*) as total
		FROM build_stats
		WHERE timestamp >= datetime('now', '-' || ? || ' days')
			AND event_type IN ('request', 'build_completed')
		GROUP BY day
		ORDER BY day DESC
	`

	rows, err := db.Query(query, days)
	if err != nil {
		return nil, fmt.Errorf("failed to query diff_packages trend: %w", err)
	}
	defer rows.Close()

	var trends []*DiffPackagesTrend
	for rows.Next() {
		var trend DiffPackagesTrend

		if err := rows.Scan(&trend.Date, &trend.DiffPackagesTrue, &trend.DiffPackagesFalse, &trend.Total); err != nil {
			return nil, fmt.Errorf("failed to scan row: %w", err)
		}

		trends = append(trends, &trend)
	}

	return trends, rows.Err()
}
