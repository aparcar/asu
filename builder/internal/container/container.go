package container

import (
	"context"
	"fmt"
	"io"
	"os/exec"
	"strings"
)

// Manager handles container operations
type Manager struct {
	runtime string // "podman" or "docker"
}

// NewManager creates a new container manager
func NewManager(runtime string) *Manager {
	return &Manager{
		runtime: runtime,
	}
}

// ContainerRunOptions holds options for running a container
type ContainerRunOptions struct {
	Image       string
	Name        string
	Mounts      []Mount
	Environment map[string]string
	WorkDir     string
	Command     []string
	Remove      bool // Remove container after exit
}

// Mount represents a volume mount
type Mount struct {
	Source   string
	Target   string
	ReadOnly bool
}

// RunContainer runs a container and returns the output
func (m *Manager) RunContainer(ctx context.Context, opts ContainerRunOptions) (string, error) {
	args := []string{"run"}

	if opts.Remove {
		args = append(args, "--rm")
	}

	if opts.Name != "" {
		args = append(args, "--name", opts.Name)
	}

	// Add mounts
	for _, mount := range opts.Mounts {
		mountStr := fmt.Sprintf("%s:%s", mount.Source, mount.Target)
		if mount.ReadOnly {
			mountStr += ":ro"
		}
		args = append(args, "-v", mountStr)
	}

	// Add environment variables
	for key, value := range opts.Environment {
		args = append(args, "-e", fmt.Sprintf("%s=%s", key, value))
	}

	// Set working directory
	if opts.WorkDir != "" {
		args = append(args, "-w", opts.WorkDir)
	}

	// Add image
	args = append(args, opts.Image)

	// Add command
	if len(opts.Command) > 0 {
		args = append(args, opts.Command...)
	}

	cmd := exec.CommandContext(ctx, m.runtime, args...)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return string(output), fmt.Errorf("failed to run container: %w (output: %s)", err, string(output))
	}

	return string(output), nil
}

// ExecContainer executes a command in a running container
func (m *Manager) ExecContainer(ctx context.Context, containerName string, command []string) (string, error) {
	args := []string{"exec", containerName}
	args = append(args, command...)

	cmd := exec.CommandContext(ctx, m.runtime, args...)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return string(output), fmt.Errorf("failed to exec in container: %w (output: %s)", err, string(output))
	}

	return string(output), nil
}

// StopContainer stops a running container
func (m *Manager) StopContainer(ctx context.Context, containerName string) error {
	cmd := exec.CommandContext(ctx, m.runtime, "stop", containerName)
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("failed to stop container: %w", err)
	}
	return nil
}

// RemoveContainer removes a container
func (m *Manager) RemoveContainer(ctx context.Context, containerName string) error {
	cmd := exec.CommandContext(ctx, m.runtime, "rm", "-f", containerName)
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("failed to remove container: %w", err)
	}
	return nil
}

// PullImage pulls a container image
func (m *Manager) PullImage(ctx context.Context, image string) error {
	cmd := exec.CommandContext(ctx, m.runtime, "pull", image)
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("failed to pull image: %w", err)
	}
	return nil
}

// ImageExists checks if an image exists locally
func (m *Manager) ImageExists(ctx context.Context, image string) (bool, error) {
	cmd := exec.CommandContext(ctx, m.runtime, "image", "exists", image)
	err := cmd.Run()
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			// Exit code 1 means image doesn't exist
			if exitErr.ExitCode() == 1 {
				return false, nil
			}
		}
		return false, fmt.Errorf("failed to check image existence: %w", err)
	}
	return true, nil
}

// CopyFromContainer copies a file from container to host
func (m *Manager) CopyFromContainer(ctx context.Context, containerName, srcPath, dstPath string) error {
	cmd := exec.CommandContext(ctx, m.runtime, "cp", fmt.Sprintf("%s:%s", containerName, srcPath), dstPath)
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("failed to copy from container: %w", err)
	}
	return nil
}

// CopyToContainer copies a file from host to container
func (m *Manager) CopyToContainer(ctx context.Context, containerName, srcPath, dstPath string) error {
	cmd := exec.CommandContext(ctx, m.runtime, "cp", srcPath, fmt.Sprintf("%s:%s", containerName, dstPath))
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("failed to copy to container: %w", err)
	}
	return nil
}

// RunCommandInContainer runs a command in a one-off container and streams output
func (m *Manager) RunCommandInContainer(ctx context.Context, opts ContainerRunOptions, stdout, stderr io.Writer) error {
	args := []string{"run"}

	if opts.Remove {
		args = append(args, "--rm")
	}

	if opts.Name != "" {
		args = append(args, "--name", opts.Name)
	}

	// Add mounts
	for _, mount := range opts.Mounts {
		mountStr := fmt.Sprintf("%s:%s", mount.Source, mount.Target)
		if mount.ReadOnly {
			mountStr += ":ro"
		}
		args = append(args, "-v", mountStr)
	}

	// Add environment variables
	for key, value := range opts.Environment {
		args = append(args, "-e", fmt.Sprintf("%s=%s", key, value))
	}

	// Set working directory
	if opts.WorkDir != "" {
		args = append(args, "-w", opts.WorkDir)
	}

	// Add image
	args = append(args, opts.Image)

	// Add command
	if len(opts.Command) > 0 {
		args = append(args, opts.Command...)
	}

	cmd := exec.CommandContext(ctx, m.runtime, args...)
	cmd.Stdout = stdout
	cmd.Stderr = stderr

	if err := cmd.Run(); err != nil {
		return fmt.Errorf("failed to run container command: %w", err)
	}

	return nil
}

// GetImageTag returns the full image tag for an ImageBuilder
func GetImageBuilderTag(registry, version, target string) string {
	// Split target into target/subtarget
	parts := strings.Split(target, "/")
	if len(parts) != 2 {
		return ""
	}

	return fmt.Sprintf("%s:%s-%s-%s", registry, version, parts[0], parts[1])
}
