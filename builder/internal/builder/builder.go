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

// Builder handles firmware building operations
type Builder struct {
	config    *config.Config
	container *container.Manager
}

// NewBuilder creates a new builder instance
func NewBuilder(cfg *config.Config) *Builder {
	return &Builder{
		config:    cfg,
		container: container.NewManager(cfg.ContainerRuntime),
	}
}

// BuildResult contains the result of a build operation
type BuildResult struct {
	Images         []string
	Manifest       string
	BuildCommand   string
	Duration       time.Duration
	Error          error
}

// Build executes a firmware build
func (b *Builder) Build(ctx context.Context, req *models.BuildRequest) *BuildResult {
	startTime := time.Now()
	result := &BuildResult{}

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

	// Pull ImageBuilder image if needed
	exists, err := b.container.ImageExists(ctx, imageTag)
	if err != nil {
		result.Error = fmt.Errorf("failed to check image existence: %w", err)
		return result
	}
	if !exists {
		if err := b.container.PullImage(ctx, imageTag); err != nil {
			result.Error = fmt.Errorf("failed to pull image: %w", err)
			return result
		}
	}

	// Get default packages
	defaultPackages, err := b.getDefaultPackages(ctx, imageTag, req.Profile)
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
	manifest, buildCmd, err := b.buildImage(ctx, imageTag, buildDir, req, packages)
	if err != nil {
		result.Error = err
		return result
	}

	result.Manifest = manifest
	result.BuildCommand = buildCmd

	// Find built images
	images, err := b.findBuiltImages(buildDir)
	if err != nil {
		result.Error = fmt.Errorf("failed to find built images: %w", err)
		return result
	}

	result.Images = images
	result.Duration = time.Since(startTime)

	return result
}

// getDefaultPackages retrieves default packages for a profile
func (b *Builder) getDefaultPackages(ctx context.Context, imageTag, profile string) ([]string, error) {
	var stdout bytes.Buffer

	opts := container.ContainerRunOptions{
		Image:   imageTag,
		Remove:  true,
		Command: []string{"make", "info"},
	}

	if err := b.container.RunCommandInContainer(ctx, opts, &stdout, io.Discard); err != nil {
		return nil, fmt.Errorf("failed to run 'make info': %w", err)
	}

	// Parse output to extract default packages
	// The output format is typically:
	// Default Packages: package1 package2 package3...
	output := stdout.String()
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

// PackageChangesRequest is sent to the package changes service
type PackageChangesRequest struct {
	Version         string            `json:"version"`
	Target          string            `json:"target"`
	Profile         string            `json:"profile"`
	Packages        []string          `json:"packages"`
	DefaultPackages []string          `json:"default_packages"`
	DiffPackages    bool              `json:"diff_packages"`
}

// PackageChangesResponse is returned by the package changes service
type PackageChangesResponse struct {
	Packages []string `json:"packages"`
	Error    string   `json:"error,omitempty"`
}

// applyPackageChanges calls the package changes service to modify the package list
func (b *Builder) applyPackageChanges(ctx context.Context, req *models.BuildRequest, defaultPackages []string) ([]string, error) {
	// If no package changes service is configured, return packages as-is
	if b.config.PackageChangesURL == "" {
		return req.Packages, nil
	}

	reqBody := PackageChangesRequest{
		Version:         req.Version,
		Target:          req.Target,
		Profile:         req.Profile,
		Packages:        req.Packages,
		DefaultPackages: defaultPackages,
		DiffPackages:    req.DiffPackages,
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
		// If service is unavailable, fall back to original packages
		return req.Packages, nil
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return req.Packages, nil
	}

	var result PackageChangesResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	if result.Error != "" {
		return nil, fmt.Errorf("package changes service error: %s", result.Error)
	}

	return result.Packages, nil
}

// buildImage builds the firmware image
func (b *Builder) buildImage(ctx context.Context, imageTag, buildDir string, req *models.BuildRequest, packages []string) (string, string, error) {
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

	var stdout, stderr bytes.Buffer

	opts := container.ContainerRunOptions{
		Image:   imageTag,
		Remove:  true,
		Mounts:  mounts,
		Command: makeArgs,
	}

	// Run the build
	if err := b.container.RunCommandInContainer(ctx, opts, &stdout, &stderr); err != nil {
		return "", buildCmd, fmt.Errorf("build failed: %w\nStdout: %s\nStderr: %s", err, stdout.String(), stderr.String())
	}

	// Get manifest
	manifestOpts := container.ContainerRunOptions{
		Image:   imageTag,
		Remove:  true,
		Command: []string{"make", "manifest", fmt.Sprintf("PROFILE=%s", req.Profile)},
	}

	var manifestOut bytes.Buffer
	if err := b.container.RunCommandInContainer(ctx, manifestOpts, &manifestOut, io.Discard); err != nil {
		return "", buildCmd, fmt.Errorf("failed to get manifest: %w", err)
	}

	return manifestOut.String(), buildCmd, nil
}

// findBuiltImages finds all built firmware images in the build directory
func (b *Builder) findBuiltImages(buildDir string) ([]string, error) {
	var images []string

	// Images are typically in bin/targets/<target>/<subtarget>/
	err := filepath.Walk(buildDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}

		if info.IsDir() {
			return nil
		}

		// Look for firmware image files (typically .bin, .img, .tar.gz, etc.)
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

	if err != nil {
		return nil, err
	}

	return images, nil
}
