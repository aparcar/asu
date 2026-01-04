.PHONY: build run clean test install deps

# Build the application
build:
	go build -o asu-builder ./cmd

# Build for production (optimized)
build-prod:
	CGO_ENABLED=1 go build -ldflags="-s -w" -trimpath -o asu-builder ./cmd

# Run the application
run: build
	./asu-builder

# Clean build artifacts
clean:
	rm -f asu-builder
	rm -rf data/

# Run tests
test:
	go test -v ./...

# Install dependencies
deps:
	go mod download
	go mod tidy

# Format code
fmt:
	go fmt ./...

# Run linter
lint:
	golangci-lint run

# Build container image
container:
	podman build -t asu-builder:latest -f Containerfile .

# Run database migrations
migrate:
	@echo "Migrations run automatically on startup"
