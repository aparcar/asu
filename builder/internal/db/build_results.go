package db

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"github.com/aparcar/asu/builder/internal/models"
)

// CreateBuildResult inserts a new build result
func (db *DB) CreateBuildResult(result *models.BuildResult) error {
	query := `
		INSERT INTO build_results (
			request_hash, images, manifest, build_at, cache_hit, build_duration_seconds
		) VALUES (?, ?, ?, ?, ?, ?)
	`

	_, err := db.Exec(query,
		result.RequestHash,
		result.Images,
		result.Manifest,
		result.BuildAt,
		result.CacheHit,
		result.BuildDurationSecs,
	)

	if err != nil {
		return fmt.Errorf("failed to insert build result: %w", err)
	}

	return nil
}

// GetBuildResult retrieves a build result by request hash
func (db *DB) GetBuildResult(requestHash string) (*models.BuildResult, error) {
	query := `
		SELECT request_hash, images, manifest, build_at, cache_hit, build_duration_seconds
		FROM build_results
		WHERE request_hash = ?
	`

	var result models.BuildResult

	err := db.QueryRow(query, requestHash).Scan(
		&result.RequestHash,
		&result.Images,
		&result.Manifest,
		&result.BuildAt,
		&result.CacheHit,
		&result.BuildDurationSecs,
	)

	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query build result: %w", err)
	}

	return &result, nil
}

// BuildResultExists checks if a build result exists
func (db *DB) BuildResultExists(requestHash string) (bool, error) {
	var count int
	err := db.QueryRow("SELECT COUNT(*) FROM build_results WHERE request_hash = ?", requestHash).Scan(&count)
	if err != nil {
		return false, err
	}
	return count > 0, nil
}

// SaveBuildImages saves the list of built images
func (db *DB) SaveBuildImages(requestHash string, images []string) error {
	imagesJSON, err := json.Marshal(images)
	if err != nil {
		return fmt.Errorf("failed to marshal images: %w", err)
	}

	result := &models.BuildResult{
		RequestHash: requestHash,
		Images:      string(imagesJSON),
		BuildAt:     time.Now(),
		CacheHit:    false,
	}

	return db.CreateBuildResult(result)
}
