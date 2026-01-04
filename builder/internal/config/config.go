package config

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/spf13/viper"
)

// Config holds all configuration for the builder service
type Config struct {
	// Server configuration
	ServerHost string `mapstructure:"server_host"`
	ServerPort int    `mapstructure:"server_port"`

	// Database configuration
	DatabasePath string `mapstructure:"database_path"`

	// Storage configuration
	PublicPath   string `mapstructure:"public_path"`
	StorePath    string `mapstructure:"store_path"`

	// Upstream OpenWrt configuration
	UpstreamURL string `mapstructure:"upstream_url"`

	// Container configuration
	ContainerRuntime     string `mapstructure:"container_runtime"`      // podman or docker
	ContainerSocketPath  string `mapstructure:"container_socket_path"`
	ImageBuilderRegistry string `mapstructure:"imagebuilder_registry"`

	// Build configuration
	MaxPendingJobs     int    `mapstructure:"max_pending_jobs"`
	JobTimeoutSeconds  int    `mapstructure:"job_timeout_seconds"`
	BuildTTLSeconds    int    `mapstructure:"build_ttl_seconds"`
	FailureTTLSeconds  int    `mapstructure:"failure_ttl_seconds"`
	AllowDefaults      bool   `mapstructure:"allow_defaults"`
	BuildKey           string `mapstructure:"build_key"`

	// Worker configuration
	WorkerID         string `mapstructure:"worker_id"`
	WorkerConcurrent int    `mapstructure:"worker_concurrent"`
	WorkerPollSecs   int    `mapstructure:"worker_poll_seconds"`

	// Package changes service
	PackageChangesURL string `mapstructure:"package_changes_url"`

	// Logging
	LogLevel string `mapstructure:"log_level"`
}

// LoadConfig loads configuration from environment and config file
func LoadConfig() (*Config, error) {
	v := viper.New()

	// Set defaults
	setDefaults(v)

	// Read from environment variables
	v.AutomaticEnv()
	v.SetEnvPrefix("ASU")

	// Try to read config file
	v.SetConfigName("config")
	v.SetConfigType("yaml")
	v.AddConfigPath("/etc/asu/")
	v.AddConfigPath("$HOME/.asu")
	v.AddConfigPath(".")

	// Config file is optional
	if err := v.ReadInConfig(); err != nil {
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return nil, fmt.Errorf("failed to read config file: %w", err)
		}
	}

	var config Config
	if err := v.Unmarshal(&config); err != nil {
		return nil, fmt.Errorf("failed to unmarshal config: %w", err)
	}

	// Expand paths
	if err := config.expandPaths(); err != nil {
		return nil, fmt.Errorf("failed to expand paths: %w", err)
	}

	return &config, nil
}

func setDefaults(v *viper.Viper) {
	// Server defaults
	v.SetDefault("server_host", "0.0.0.0")
	v.SetDefault("server_port", 8080)

	// Database defaults
	v.SetDefault("database_path", "./data/builder.db")

	// Storage defaults
	v.SetDefault("public_path", "./public")
	v.SetDefault("store_path", "./public/store")

	// Upstream defaults
	v.SetDefault("upstream_url", "https://downloads.openwrt.org")

	// Container defaults
	v.SetDefault("container_runtime", "podman")
	v.SetDefault("container_socket_path", "/run/podman/podman.sock")
	v.SetDefault("imagebuilder_registry", "ghcr.io/openwrt/imagebuilder")

	// Build defaults
	v.SetDefault("max_pending_jobs", 200)
	v.SetDefault("job_timeout_seconds", 600) // 10 minutes
	v.SetDefault("build_ttl_seconds", 86400) // 1 day
	v.SetDefault("failure_ttl_seconds", 3600) // 1 hour
	v.SetDefault("allow_defaults", true)
	v.SetDefault("build_key", "")

	// Worker defaults
	hostname, _ := os.Hostname()
	v.SetDefault("worker_id", hostname)
	v.SetDefault("worker_concurrent", 4)
	v.SetDefault("worker_poll_seconds", 5)

	// Package changes service
	v.SetDefault("package_changes_url", "http://localhost:8081")

	// Logging
	v.SetDefault("log_level", "info")
}

func (c *Config) expandPaths() error {
	var err error

	c.DatabasePath, err = expandPath(c.DatabasePath)
	if err != nil {
		return fmt.Errorf("failed to expand database_path: %w", err)
	}

	c.PublicPath, err = expandPath(c.PublicPath)
	if err != nil {
		return fmt.Errorf("failed to expand public_path: %w", err)
	}

	c.StorePath, err = expandPath(c.StorePath)
	if err != nil {
		return fmt.Errorf("failed to expand store_path: %w", err)
	}

	if c.BuildKey != "" {
		c.BuildKey, err = expandPath(c.BuildKey)
		if err != nil {
			return fmt.Errorf("failed to expand build_key: %w", err)
		}
	}

	return nil
}

func expandPath(path string) (string, error) {
	if path == "" {
		return "", nil
	}

	// Expand home directory
	if path[:2] == "~/" {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		path = filepath.Join(home, path[2:])
	}

	// Get absolute path
	absPath, err := filepath.Abs(path)
	if err != nil {
		return "", err
	}

	return absPath, nil
}

// Validate checks if the configuration is valid
func (c *Config) Validate() error {
	if c.ServerPort < 1 || c.ServerPort > 65535 {
		return fmt.Errorf("invalid server port: %d", c.ServerPort)
	}

	if c.UpstreamURL == "" {
		return fmt.Errorf("upstream_url is required")
	}

	if c.ContainerRuntime != "podman" && c.ContainerRuntime != "docker" {
		return fmt.Errorf("container_runtime must be 'podman' or 'docker'")
	}

	if c.MaxPendingJobs < 1 {
		return fmt.Errorf("max_pending_jobs must be at least 1")
	}

	return nil
}
