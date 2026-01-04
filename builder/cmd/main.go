package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/aparcar/asu/builder/internal/api"
	"github.com/aparcar/asu/builder/internal/builder"
	"github.com/aparcar/asu/builder/internal/config"
	"github.com/aparcar/asu/builder/internal/db"
	"github.com/aparcar/asu/builder/internal/queue"
)

func main() {
	// Load configuration
	cfg, err := config.LoadConfig()
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	if err := cfg.Validate(); err != nil {
		log.Fatalf("Invalid configuration: %v", err)
	}

	log.Printf("Starting ASU Builder (Go)")
	log.Printf("Database: %s", cfg.DatabasePath)
	log.Printf("Storage: %s", cfg.StorePath)
	log.Printf("Server: %s:%d", cfg.ServerHost, cfg.ServerPort)

	// Initialize database
	database, err := db.NewDB(cfg.DatabasePath)
	if err != nil {
		log.Fatalf("Failed to initialize database: %v", err)
	}
	defer database.Close()
	log.Println("Database initialized successfully")

	// Initialize builder
	bldr, err := builder.NewBuilderWithPodman(cfg)
	if err != nil {
		log.Fatalf("Failed to initialize builder: %v", err)
	}
	log.Println("Builder initialized successfully")

	// Create context for graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start worker goroutines
	log.Printf("Starting %d worker(s)", cfg.WorkerConcurrent)
	worker := queue.NewWorker(database, bldr, cfg)
	go worker.Start(ctx)

	// Start HTTP API server
	log.Printf("Starting HTTP server on %s:%d", cfg.ServerHost, cfg.ServerPort)
	apiServer := api.NewServer(database, cfg)

	// Handle graceful shutdown
	go func() {
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, os.Interrupt, syscall.SIGTERM)
		<-sigCh

		log.Println("Received shutdown signal, shutting down gracefully...")
		cancel()
		worker.Stop()
		os.Exit(0)
	}()

	// Start server (blocking)
	if err := apiServer.Start(); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}
