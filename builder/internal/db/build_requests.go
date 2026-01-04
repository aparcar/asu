package db

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"github.com/aparcar/asu/builder/internal/models"
)

// CreateBuildRequest inserts a new build request into the database
func (db *DB) CreateBuildRequest(req *models.BuildRequest) error {
	packagesJSON, err := req.PackagesJSON()
	if err != nil {
		return fmt.Errorf("failed to marshal packages: %w", err)
	}

	packagesVersionsJSON, err := req.PackagesVersionsJSON()
	if err != nil {
		return fmt.Errorf("failed to marshal packages_versions: %w", err)
	}

	repositoriesJSON, err := req.RepositoriesJSON()
	if err != nil {
		return fmt.Errorf("failed to marshal repositories: %w", err)
	}

	repositoryKeysJSON, err := req.RepositoryKeysJSON()
	if err != nil {
		return fmt.Errorf("failed to marshal repository_keys: %w", err)
	}

	query := `
		INSERT INTO build_requests (
			request_hash, distro, version, target, profile,
			packages, packages_versions, defaults, rootfs_size_mb,
			repositories, repository_keys, diff_packages, client, created_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`

	_, err = db.Exec(query,
		req.RequestHash,
		req.Distro,
		req.Version,
		req.Target,
		req.Profile,
		packagesJSON,
		packagesVersionsJSON,
		req.Defaults,
		req.RootfsSizeMB,
		repositoriesJSON,
		repositoryKeysJSON,
		req.DiffPackages,
		req.Client,
		req.CreatedAt,
	)

	if err != nil {
		return fmt.Errorf("failed to insert build request: %w", err)
	}

	return nil
}

// GetBuildRequest retrieves a build request by hash
func (db *DB) GetBuildRequest(requestHash string) (*models.BuildRequest, error) {
	query := `
		SELECT request_hash, distro, version, target, profile,
			   packages, packages_versions, defaults, rootfs_size_mb,
			   repositories, repository_keys, diff_packages, client, created_at
		FROM build_requests
		WHERE request_hash = ?
	`

	var req models.BuildRequest
	var packagesJSON, packagesVersionsJSON, repositoriesJSON, repositoryKeysJSON string

	err := db.QueryRow(query, requestHash).Scan(
		&req.RequestHash,
		&req.Distro,
		&req.Version,
		&req.Target,
		&req.Profile,
		&packagesJSON,
		&packagesVersionsJSON,
		&req.Defaults,
		&req.RootfsSizeMB,
		&repositoriesJSON,
		&repositoryKeysJSON,
		&req.DiffPackages,
		&req.Client,
		&req.CreatedAt,
	)

	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query build request: %w", err)
	}

	// Unmarshal JSON fields
	if err := json.Unmarshal([]byte(packagesJSON), &req.Packages); err != nil {
		return nil, fmt.Errorf("failed to unmarshal packages: %w", err)
	}
	if err := json.Unmarshal([]byte(packagesVersionsJSON), &req.PackagesVersions); err != nil {
		return nil, fmt.Errorf("failed to unmarshal packages_versions: %w", err)
	}
	if err := json.Unmarshal([]byte(repositoriesJSON), &req.Repositories); err != nil {
		return nil, fmt.Errorf("failed to unmarshal repositories: %w", err)
	}
	if err := json.Unmarshal([]byte(repositoryKeysJSON), &req.RepositoryKeys); err != nil {
		return nil, fmt.Errorf("failed to unmarshal repository_keys: %w", err)
	}

	return &req, nil
}

// BuildRequestExists checks if a build request exists
func (db *DB) BuildRequestExists(requestHash string) (bool, error) {
	var count int
	err := db.QueryRow("SELECT COUNT(*) FROM build_requests WHERE request_hash = ?", requestHash).Scan(&count)
	if err != nil {
		return false, err
	}
	return count > 0, nil
}
