package models

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"
)

// BuildRequest represents a firmware build request
type BuildRequest struct {
	RequestHash      string            `json:"request_hash" db:"request_hash"`
	Distro           string            `json:"distro" db:"distro" binding:"required"`
	Version          string            `json:"version" db:"version" binding:"required"`
	Target           string            `json:"target" db:"target" binding:"required"`
	Profile          string            `json:"profile" db:"profile" binding:"required"`
	Packages         []string          `json:"packages,omitempty" db:"packages"`
	PackagesVersions map[string]string `json:"packages_versions,omitempty" db:"packages_versions"`
	Defaults         string            `json:"defaults,omitempty" db:"defaults"`
	RootfsSizeMB     int               `json:"rootfs_size_mb,omitempty" db:"rootfs_size_mb"`
	Repositories     []string          `json:"repositories,omitempty" db:"repositories"`
	RepositoryKeys   []string          `json:"repository_keys,omitempty" db:"repository_keys"`
	DiffPackages     bool              `json:"diff_packages,omitempty" db:"diff_packages"`
	Client           string            `json:"client,omitempty" db:"client"`
	CreatedAt        time.Time         `json:"created_at" db:"created_at"`
}

// ComputeHash calculates the deterministic hash for this build request
func (br *BuildRequest) ComputeHash() string {
	// Normalize and sort packages for consistent hashing
	packages := make([]string, len(br.Packages))
	copy(packages, br.Packages)
	sort.Strings(packages)

	// Create hash input
	hashInput := fmt.Sprintf("%s:%s:%s:%s:%s:%v:%d",
		br.Distro,
		br.Version,
		br.Target,
		br.Profile,
		strings.Join(packages, ","),
		br.DiffPackages,
		br.RootfsSizeMB,
	)

	// Add package versions if present
	if len(br.PackagesVersions) > 0 {
		keys := make([]string, 0, len(br.PackagesVersions))
		for k := range br.PackagesVersions {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		for _, k := range keys {
			hashInput += fmt.Sprintf(":%s=%s", k, br.PackagesVersions[k])
		}
	}

	// Add repositories if present
	if len(br.Repositories) > 0 {
		hashInput += ":" + strings.Join(br.Repositories, ",")
	}

	// Add defaults if present
	if br.Defaults != "" {
		hashInput += ":" + br.Defaults
	}

	hash := sha256.Sum256([]byte(hashInput))
	return fmt.Sprintf("%x", hash)
}

// PackagesJSON returns packages as JSON string for database storage
func (br *BuildRequest) PackagesJSON() (string, error) {
	if len(br.Packages) == 0 {
		return "[]", nil
	}
	data, err := json.Marshal(br.Packages)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

// PackagesVersionsJSON returns packages_versions as JSON string for database storage
func (br *BuildRequest) PackagesVersionsJSON() (string, error) {
	if len(br.PackagesVersions) == 0 {
		return "{}", nil
	}
	data, err := json.Marshal(br.PackagesVersions)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

// RepositoriesJSON returns repositories as JSON string for database storage
func (br *BuildRequest) RepositoriesJSON() (string, error) {
	if len(br.Repositories) == 0 {
		return "[]", nil
	}
	data, err := json.Marshal(br.Repositories)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

// RepositoryKeysJSON returns repository_keys as JSON string for database storage
func (br *BuildRequest) RepositoryKeysJSON() (string, error) {
	if len(br.RepositoryKeys) == 0 {
		return "[]", nil
	}
	data, err := json.Marshal(br.RepositoryKeys)
	if err != nil {
		return "", err
	}
	return string(data), nil
}
