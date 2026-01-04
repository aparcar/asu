package container

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"github.com/containers/podman/v4/pkg/bindings"
	"github.com/containers/podman/v4/pkg/bindings/containers"
	"github.com/containers/podman/v4/pkg/bindings/images"
	"github.com/containers/podman/v4/pkg/specgen"
)

// PodmanManager handles container operations using Podman bindings
type PodmanManager struct {
	ctx context.Context
}

// NewPodmanManager creates a new Podman manager
func NewPodmanManager(socketPath string) (*PodmanManager, error) {
	// Connect to Podman socket
	connText := fmt.Sprintf("unix://%s", socketPath)
	ctx, err := bindings.NewConnection(context.Background(), connText)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to Podman: %w", err)
	}

	return &PodmanManager{ctx: ctx}, nil
}

// ContainerRunOptions holds options for running a container
type ContainerRunOptions struct {
	Image       string
	Name        string
	Mounts      []Mount
	Environment map[string]string
	WorkDir     string
	Command     []string
	Remove      bool
}

// Mount represents a volume mount
type Mount struct {
	Source   string
	Target   string
	ReadOnly bool
}

// RunContainer runs a container and waits for it to complete
func (m *PodmanManager) RunContainer(opts ContainerRunOptions) (string, error) {
	// Pull image if needed
	exists, err := m.ImageExists(opts.Image)
	if err != nil {
		return "", err
	}
	if !exists {
		if err := m.PullImage(opts.Image); err != nil {
			return "", err
		}
	}

	// Create container spec
	spec := &specgen.SpecGenerator{
		ContainerBasicConfig: specgen.ContainerBasicConfig{
			Name:    opts.Name,
			Remove:  &opts.Remove,
			Command: opts.Command,
		},
		ContainerStorageConfig: specgen.ContainerStorageConfig{
			Image: opts.Image,
		},
	}

	// Add working directory
	if opts.WorkDir != "" {
		spec.WorkDir = opts.WorkDir
	}

	// Add environment variables
	if len(opts.Environment) > 0 {
		env := make(map[string]string)
		for k, v := range opts.Environment {
			env[k] = v
		}
		spec.Env = env
	}

	// Add mounts
	if len(opts.Mounts) > 0 {
		mounts := []specgen.Mount{}
		for _, mount := range opts.Mounts {
			m := specgen.Mount{
				Source:      mount.Source,
				Destination: mount.Target,
				Type:        "bind",
			}
			if mount.ReadOnly {
				m.Options = []string{"ro"}
			}
			mounts = append(mounts, m)
		}
		spec.Mounts = mounts
	}

	// Create container
	createResponse, err := containers.CreateWithSpec(m.ctx, spec, nil)
	if err != nil {
		return "", fmt.Errorf("failed to create container: %w", err)
	}

	containerID := createResponse.ID

	// Start container
	if err := containers.Start(m.ctx, containerID, nil); err != nil {
		return "", fmt.Errorf("failed to start container: %w", err)
	}

	// Wait for container to finish
	waitChan := make(chan error)
	go func() {
		_, err := containers.Wait(m.ctx, containerID, nil)
		waitChan <- err
	}()

	// Get logs
	logOptions := &containers.LogOptions{
		Stdout: bindings.PTrue,
		Stderr: bindings.PTrue,
		Follow: bindings.PTrue,
	}

	logChan, err := containers.Logs(m.ctx, containerID, logOptions)
	if err != nil {
		return "", fmt.Errorf("failed to get container logs: %w", err)
	}

	// Collect logs
	var output strings.Builder
	for line := range logChan {
		output.WriteString(line)
	}

	// Wait for container to finish
	if err := <-waitChan; err != nil {
		return output.String(), fmt.Errorf("container execution failed: %w", err)
	}

	// Check exit code
	inspectData, err := containers.Inspect(m.ctx, containerID, nil)
	if err != nil {
		return output.String(), fmt.Errorf("failed to inspect container: %w", err)
	}

	if inspectData.State.ExitCode != 0 {
		return output.String(), fmt.Errorf("container exited with code %d", inspectData.State.ExitCode)
	}

	return output.String(), nil
}

// PullImage pulls a container image
func (m *PodmanManager) PullImage(image string) error {
	_, err := images.Pull(m.ctx, image, nil)
	if err != nil {
		return fmt.Errorf("failed to pull image: %w", err)
	}
	return nil
}

// ImageExists checks if an image exists locally
func (m *PodmanManager) ImageExists(image string) (bool, error) {
	exists, err := images.Exists(m.ctx, image, nil)
	if err != nil {
		return false, fmt.Errorf("failed to check image existence: %w", err)
	}
	return exists, nil
}

// CopyFromContainer copies files from container to host
func (m *PodmanManager) CopyFromContainer(containerID, srcPath, dstPath string) error {
	reader, _, err := containers.CopyFromArchive(m.ctx, containerID, srcPath, nil)
	if err != nil {
		return fmt.Errorf("failed to copy from container: %w", err)
	}
	defer reader.Close()

	// Create destination directory
	if err := os.MkdirAll(filepath.Dir(dstPath), 0755); err != nil {
		return fmt.Errorf("failed to create destination directory: %w", err)
	}

	// Write to destination
	out, err := os.Create(dstPath)
	if err != nil {
		return fmt.Errorf("failed to create destination file: %w", err)
	}
	defer out.Close()

	if _, err := io.Copy(out, reader); err != nil {
		return fmt.Errorf("failed to write file: %w", err)
	}

	return nil
}

// RemoveContainer removes a container
func (m *PodmanManager) RemoveContainer(containerID string) error {
	_, err := containers.Remove(m.ctx, containerID, nil)
	return err
}

// GetImageBuilderTag returns the full image tag for an ImageBuilder
func GetImageBuilderTag(registry, version, target string) string {
	// Split target into target/subtarget
	parts := strings.Split(target, "/")
	if len(parts) != 2 {
		return ""
	}

	return fmt.Sprintf("%s:%s-%s-%s", registry, version, parts[0], parts[1])
}
