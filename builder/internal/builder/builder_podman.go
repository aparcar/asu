package builder

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/aparcar/asu/builder/internal/config"
	"github.com/aparcar/asu/builder/internal/container"
	"github.com/aparcar/asu/builder/internal/models"
)

// BuilderWithPodman handles firmware building operations using Podman bindings
type BuilderWithPodman struct {
	config  *config.Config
	podman  *container.PodmanManager
}

// NewBuilderWithPodman creates a new builder instance using Podman bindings
func NewBuilderWithPodman(cfg *config.Config) (*BuilderWithPodman, error) {
	podman, err := container.NewPodmanManager(cfg.ContainerSocketPath)
	if err != nil {
		return nil, fmt.Errorf("failed to create Podman manager: %w", err)
	}

	return &BuilderWithPodman{
		config: cfg,
		podman: podman,
	}, nil
}

// BuildResult contains the result of a build operation
type BuildResultPodman struct {
	Images         []string
	Manifest       string
	BuildCommand   string
	Duration       time.Duration
	Error          error
}

// Build executes a firmware build using Podman bindings
func (b *BuilderWithPodman) Build(ctx context.Context, req *models.BuildRequest) *BuildResultPodman {
	startTime := time.Now()
	result := &BuildResultPodman{}

	// Create build directory
	buildDir := filepath.Join(b.config.StorePath, req.RequestHash)
	if err := os.MkdirAll(buildDir, 0755); err != nil {
		result.Error = fmt.Errorf("failed to create build directory: %w", err)
		return result
	}

	// Get ImageBuilder image tag
	imageTag := container.GetImageBuilderTag(
		b.config.ImageBuilderRegistry,
		req.Version,
		req.Target,
	)
	if imageTag == "" {
		result.Error = fmt.Errorf("invalid target format: %s", req.Target)
		return result
	}

	// Get default packages
	defaultPackages, err := b.getDefaultPackages(imageTag, req.Profile)
	if err != nil {
		result.Error = fmt.Errorf("failed to get default packages: %w", err)
		return result
	}

	// Apply package changes (call external service)
	packages, err := b.applyPackageChanges(ctx, req, defaultPackages)
	if err != nil {
		result.Error = fmt.Errorf("failed to apply package changes: %w", err)
		return result
	}

	// Build the image
	manifest, buildCmd, err := b.buildImage(imageTag, buildDir, req, packages)
	if err != nil {
		result.Error = err
		return result
	}

	result.Manifest = manifest
	result.BuildCommand = buildCmd

	// Find built images
	images, err := findBuiltImages(buildDir)
	if err != nil {
		result.Error = fmt.Errorf("failed to find built images: %w", err)
		return result
	}

	result.Images = images
	result.Duration = time.Since(startTime)

	return result
}

// getDefaultPackages retrieves default packages for a profile
func (b *BuilderWithPodman) getDefaultPackages(imageTag, profile string) ([]string, error) {
	opts := container.ContainerRunOptions{
		Image:   imageTag,
		Remove:  true,
		Command: []string{"make", "info"},
	}

	output, err := b.podman.RunContainer(opts)
	if err != nil {
		return nil, fmt.Errorf("failed to run 'make info': %w", err)
	}

	// Parse output to extract default packages
	lines := strings.Split(output, "\n")
	for _, line := range lines {
		if strings.HasPrefix(line, "Default Packages:") {
			packagesStr := strings.TrimPrefix(line, "Default Packages:")
			packagesStr = strings.TrimSpace(packagesStr)
			return strings.Fields(packagesStr), nil
		}
	}

	return []string{}, nil
}

// applyPackageChanges calls the package changes service
func (b *BuilderWithPodman) applyPackageChanges(ctx context.Context, req *models.BuildRequest, defaultPackages []string) ([]string, error) {
	if b.config.PackageChangesURL == "" {
		return req.Packages, nil
	}

	reqBody := map[string]interface{}{
		"version":          req.Version,
		"target":           req.Target,
		"profile":          req.Profile,
		"packages":         req.Packages,
		"default_packages": defaultPackages,
		"diff_packages":    req.DiffPackages,
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", b.config.PackageChangesURL+"/apply", bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(httpReq)
	if err != nil {
		return req.Packages, nil // Fallback
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return req.Packages, nil
	}

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	if errMsg, ok := result["error"].(string); ok && errMsg != "" {
		return nil, fmt.Errorf("package changes service error: %s", errMsg)
	}

	if pkgs, ok := result["packages"].([]interface{}); ok {
		packages := make([]string, len(pkgs))
		for i, p := range pkgs {
			packages[i] = p.(string)
		}
		return packages, nil
	}

	return req.Packages, nil
}

// buildImage builds the firmware image
func (b *BuilderWithPodman) buildImage(imageTag, buildDir string, req *models.BuildRequest, packages []string) (string, string, error) {
	// Prepare build command
	makeArgs := []string{"make", "image"}
	makeArgs = append(makeArgs, fmt.Sprintf("PROFILE=%s", req.Profile))

	if len(packages) > 0 {
		makeArgs = append(makeArgs, fmt.Sprintf("PACKAGES=%s", strings.Join(packages, " ")))
	}

	if req.RootfsSizeMB > 0 {
		makeArgs = append(makeArgs, fmt.Sprintf("ROOTFS_PARTSIZE=%d", req.RootfsSizeMB))
	}

	buildCmd := strings.Join(makeArgs, " ")

	// Setup mounts
	mounts := []container.Mount{
		{
			Source:   buildDir,
			Target:   "/builder/bin",
			ReadOnly: false,
		},
	}

	// Add defaults file if provided
	if req.Defaults != "" && b.config.AllowDefaults {
		defaultsFile := filepath.Join(buildDir, "files", "etc", "uci-defaults", "99-custom")
		if err := os.MkdirAll(filepath.Dir(defaultsFile), 0755); err != nil {
			return "", buildCmd, fmt.Errorf("failed to create defaults directory: %w", err)
		}
		if err := os.WriteFile(defaultsFile, []byte(req.Defaults), 0755); err != nil {
			return "", buildCmd, fmt.Errorf("failed to write defaults file: %w", err)
		}

		mounts = append(mounts, container.Mount{
			Source:   filepath.Join(buildDir, "files"),
			Target:   "/builder/files",
			ReadOnly: true,
		})
	}

	opts := container.ContainerRunOptions{
		Image:   imageTag,
		Remove:  true,
		Mounts:  mounts,
		Command: makeArgs,
	}

	// Run the build
	_, err := b.podman.RunContainer(opts)
	if err != nil {
		return "", buildCmd, fmt.Errorf("build failed: %w", err)
	}

	// Get manifest
	manifestOpts := container.ContainerRunOptions{
		Image:   imageTag,
		Remove:  true,
		Command: []string{"make", "manifest", fmt.Sprintf("PROFILE=%s", req.Profile)},
	}

	manifest, err := b.podman.RunContainer(manifestOpts)
	if err != nil {
		return "", buildCmd, fmt.Errorf("failed to get manifest: %w", err)
	}

	return manifest, buildCmd, nil
}

// findBuiltImages finds all built firmware images in the build directory
func findBuiltImages(buildDir string) ([]string, error) {
	var images []string

	err := filepath.Walk(buildDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}

		if info.IsDir() {
			return nil
		}

		// Look for firmware image files
		ext := filepath.Ext(path)
		if ext == ".bin" || ext == ".img" || ext == ".gz" || ext == ".trx" {
			relPath, err := filepath.Rel(buildDir, path)
			if err != nil {
				return err
			}
			images = append(images, relPath)
		}

		return nil
	})

	return images, err
}
