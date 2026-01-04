package queue

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"time"

	"github.com/aparcar/asu/builder/internal/builder"
	"github.com/aparcar/asu/builder/internal/config"
	"github.com/aparcar/asu/builder/internal/db"
	"github.com/aparcar/asu/builder/internal/models"
)

// Worker processes build jobs from the queue
type Worker struct {
	db      *db.DB
	builder *builder.BuilderWithPodman
	config  *config.Config
	stopCh  chan struct{}
}

// NewWorker creates a new worker instance
func NewWorker(database *db.DB, bldr *builder.BuilderWithPodman, cfg *config.Config) *Worker {
	return &Worker{
		db:      database,
		builder: bldr,
		config:  cfg,
		stopCh:  make(chan struct{}),
	}
}

// Start begins processing jobs from the queue
func (w *Worker) Start(ctx context.Context) {
	ticker := time.NewTicker(time.Duration(w.config.WorkerPollSecs) * time.Second)
	defer ticker.Stop()

	log.Printf("Worker %s started, polling every %d seconds", w.config.WorkerID, w.config.WorkerPollSecs)

	// Process immediately on start
	w.processJobs(ctx)

	for {
		select {
		case <-ctx.Done():
			log.Println("Worker shutting down...")
			return
		case <-w.stopCh:
			log.Println("Worker stopped")
			return
		case <-ticker.C:
			w.processJobs(ctx)
		}
	}
}

// Stop signals the worker to stop
func (w *Worker) Stop() {
	close(w.stopCh)
}

// processJobs fetches and processes pending jobs
func (w *Worker) processJobs(ctx context.Context) {
	jobs, err := w.db.GetPendingJobs()
	if err != nil {
		log.Printf("Failed to get pending jobs: %v", err)
		return
	}

	if len(jobs) == 0 {
		return
	}

	log.Printf("Found %d pending job(s)", len(jobs))

	// Process jobs up to worker concurrency limit
	limit := w.config.WorkerConcurrent
	if len(jobs) < limit {
		limit = len(jobs)
	}

	for i := 0; i < limit; i++ {
		job := jobs[i]
		go w.processJob(ctx, job)
	}
}

// processJob processes a single build job
func (w *Worker) processJob(ctx context.Context, job *models.BuildJob) {
	log.Printf("Processing job %s (request_hash: %s)", job.ID, job.RequestHash)

	// Mark job as building
	if err := w.db.StartBuildJob(job.RequestHash, w.config.WorkerID); err != nil {
		log.Printf("Failed to start job %s: %v", job.RequestHash, err)
		return
	}

	// Get build request
	buildReq, err := w.db.GetBuildRequest(job.RequestHash)
	if err != nil {
		log.Printf("Failed to get build request %s: %v", job.RequestHash, err)
		w.db.FailBuildJob(job.RequestHash, fmt.Sprintf("Failed to get build request: %v", err))
		return
	}

	if buildReq == nil {
		log.Printf("Build request %s not found", job.RequestHash)
		w.db.FailBuildJob(job.RequestHash, "Build request not found")
		return
	}

	// Create build context with timeout
	buildCtx, cancel := context.WithTimeout(ctx, time.Duration(w.config.JobTimeoutSeconds)*time.Second)
	defer cancel()

	// Execute build
	startTime := time.Now()
	result := w.builder.Build(buildCtx, buildReq)
	duration := time.Since(startTime)

	if result.Error != nil {
		log.Printf("Build failed for %s: %v", job.RequestHash, result.Error)
		if err := w.db.FailBuildJob(job.RequestHash, result.Error.Error()); err != nil {
			log.Printf("Failed to mark job as failed: %v", err)
		}

		// Record failure stat
		w.db.RecordEvent(models.EventTypeFailure, buildReq.Version, buildReq.Target, buildReq.Profile, 0)
		return
	}

	// Save build result
	buildResult := &models.BuildResult{
		RequestHash:       job.RequestHash,
		BuildAt:           time.Now(),
		CacheHit:          false,
		BuildDurationSecs: int(duration.Seconds()),
	}

	// Marshal images to JSON
	if len(result.Images) > 0 {
		imagesJSON, err := json.Marshal(result.Images)
		if err != nil {
			log.Printf("Failed to marshal images: %v", err)
		} else {
			buildResult.Images = string(imagesJSON)
		}
	}

	buildResult.Manifest = result.Manifest

	if err := w.db.CreateBuildResult(buildResult); err != nil {
		log.Printf("Failed to save build result: %v", err)
	}

	// Mark job as completed
	if err := w.db.CompleteBuildJob(job.RequestHash, result.BuildCommand, result.Manifest); err != nil {
		log.Printf("Failed to mark job as completed: %v", err)
		return
	}

	// Record success stat
	w.db.RecordEvent(models.EventTypeBuildCompleted, buildReq.Version, buildReq.Target, buildReq.Profile, int(duration.Seconds()))

	log.Printf("Build completed for %s in %v, images: %v", job.RequestHash, duration, result.Images)
}

// EnqueueJob adds a new build job to the queue
func EnqueueJob(database *db.DB, req *models.BuildRequest) error {
	// Check if already in queue or completed
	existingJob, err := database.GetBuildJob(req.RequestHash)
	if err != nil {
		return fmt.Errorf("failed to check existing job: %w", err)
	}

	// If job exists and is pending or building, don't enqueue again
	if existingJob != nil {
		if existingJob.Status == models.JobStatusPending || existingJob.Status == models.JobStatusBuilding {
			return nil // Already queued
		}
	}

	// Check if result already exists (cached build)
	resultExists, err := database.BuildResultExists(req.RequestHash)
	if err != nil {
		return fmt.Errorf("failed to check build result: %w", err)
	}

	if resultExists {
		return nil // Already built, no need to enqueue
	}

	// Get current queue position
	queueLen, err := database.GetQueueLength()
	if err != nil {
		return fmt.Errorf("failed to get queue length: %w", err)
	}

	// Create new job
	job := &models.BuildJob{
		RequestHash:   req.RequestHash,
		Status:        models.JobStatusPending,
		QueuePosition: queueLen + 1,
	}

	_, err = database.CreateBuildJob(job)
	if err != nil {
		return fmt.Errorf("failed to create build job: %w", err)
	}

	log.Printf("Enqueued job for request %s at position %d", req.RequestHash, job.QueuePosition)

	return nil
}

