package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/aparcar/asu/builder/internal/config"
	"github.com/aparcar/asu/builder/internal/db"
	"github.com/aparcar/asu/builder/internal/models"
	"github.com/aparcar/asu/builder/internal/queue"
	"github.com/gin-gonic/gin"
)

// Server holds the API server components
type Server struct {
	db     *db.DB
	config *config.Config
	router *gin.Engine
}

// NewServer creates a new API server
func NewServer(database *db.DB, cfg *config.Config) *Server {
	s := &Server{
		db:     database,
		config: cfg,
	}

	// Setup router
	if cfg.LogLevel == "debug" {
		gin.SetMode(gin.DebugMode)
	} else {
		gin.SetMode(gin.ReleaseMode)
	}

	s.router = gin.Default()
	s.setupRoutes()

	return s
}

// setupRoutes configures the API routes
func (s *Server) setupRoutes() {
	// API v1 routes
	v1 := s.router.Group("/api/v1")
	{
		v1.POST("/build", s.handleBuildRequest)
		v1.GET("/build/:request_hash", s.handleBuildStatus)
		v1.GET("/stats", s.handleStats)
		v1.GET("/builds-per-day", s.handleBuildsPerDay)
		v1.GET("/builds-by-version", s.handleBuildsByVersion)
		v1.GET("/diff-packages-stats", s.handleDiffPackagesStats)
		v1.GET("/diff-packages-by-version", s.handleDiffPackagesByVersion)
		v1.GET("/diff-packages-trend", s.handleDiffPackagesTrend)
	}

	// Health check
	s.router.GET("/health", s.handleHealth)
}

// Start starts the HTTP server
func (s *Server) Start() error {
	addr := fmt.Sprintf("%s:%d", s.config.ServerHost, s.config.ServerPort)
	return s.router.Run(addr)
}

// handleBuildRequest handles POST /api/v1/build
func (s *Server) handleBuildRequest(c *gin.Context) {
	var req models.BuildRequest

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Set created timestamp
	req.CreatedAt = time.Now()

	// Compute request hash
	req.RequestHash = req.ComputeHash()

	// Check if result already exists (cache hit)
	result, err := s.db.GetBuildResult(req.RequestHash)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("Failed to check cache: %v", err)})
		return
	}

	if result != nil {
		// Cache hit - return existing result
		s.db.RecordEvent(models.EventTypeCacheHit, req.Version, req.Target, req.Profile, 0, req.DiffPackages)

		var images []string
		json.Unmarshal([]byte(result.Images), &images)

		response := models.BuildResponse{
			RequestHash:   req.RequestHash,
			Status:        models.JobStatusCompleted,
			Images:        images,
			Manifest:      result.Manifest,
			BuildDuration: result.BuildDurationSecs,
			CacheHit:      true,
		}

		c.JSON(http.StatusOK, response)
		return
	}

	// Check if job is already queued
	job, err := s.db.GetBuildJob(req.RequestHash)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("Failed to check job status: %v", err)})
		return
	}

	if job != nil && (job.Status == models.JobStatusPending || job.Status == models.JobStatusBuilding) {
		// Job already queued
		position, _ := s.db.GetQueuePosition(req.RequestHash)
		response := models.BuildResponse{
			RequestHash:   req.RequestHash,
			Status:        job.Status,
			QueuePosition: position,
			StartedAt:     job.StartedAt,
		}
		c.JSON(http.StatusAccepted, response)
		return
	}

	// Check queue capacity
	queueLen, err := s.db.GetQueueLength()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get queue length"})
		return
	}

	if queueLen >= s.config.MaxPendingJobs {
		c.JSON(http.StatusTooManyRequests, gin.H{"error": "Queue is full, please try again later"})
		return
	}

	// Save build request
	exists, err := s.db.BuildRequestExists(req.RequestHash)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to check request existence"})
		return
	}

	if !exists {
		if err := s.db.CreateBuildRequest(&req); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("Failed to save request: %v", err)})
			return
		}
	}

	// Enqueue job
	if err := queue.EnqueueJob(s.db, &req); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("Failed to enqueue job: %v", err)})
		return
	}

	// Record request stat
	s.db.RecordEvent(models.EventTypeRequest, req.Version, req.Target, req.Profile, 0, req.DiffPackages)

	position, _ := s.db.GetQueuePosition(req.RequestHash)
	response := models.BuildResponse{
		RequestHash:   req.RequestHash,
		Status:        models.JobStatusPending,
		QueuePosition: position,
	}

	c.JSON(http.StatusAccepted, response)
}

// handleBuildStatus handles GET /api/v1/build/:request_hash
func (s *Server) handleBuildStatus(c *gin.Context) {
	requestHash := c.Param("request_hash")

	// Check for completed build
	result, err := s.db.GetBuildResult(requestHash)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get build result"})
		return
	}

	if result != nil {
		var images []string
		json.Unmarshal([]byte(result.Images), &images)

		response := models.BuildResponse{
			RequestHash:   requestHash,
			Status:        models.JobStatusCompleted,
			Images:        images,
			Manifest:      result.Manifest,
			BuildDuration: result.BuildDurationSecs,
			FinishedAt:    &result.BuildAt,
			CacheHit:      result.CacheHit,
		}

		c.JSON(http.StatusOK, response)
		return
	}

	// Check job status
	job, err := s.db.GetBuildJob(requestHash)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get job status"})
		return
	}

	if job == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Build not found"})
		return
	}

	position := 0
	if job.Status == models.JobStatusPending {
		position, _ = s.db.GetQueuePosition(requestHash)
	}

	response := models.BuildResponse{
		RequestHash:   requestHash,
		Status:        job.Status,
		QueuePosition: position,
		ErrorMessage:  job.ErrorMessage,
		StartedAt:     job.StartedAt,
		FinishedAt:    job.FinishedAt,
	}

	// Return appropriate status code
	switch job.Status {
	case models.JobStatusPending, models.JobStatusBuilding:
		c.JSON(http.StatusAccepted, response)
	case models.JobStatusCompleted:
		c.JSON(http.StatusOK, response)
	case models.JobStatusFailed:
		c.JSON(http.StatusInternalServerError, response)
	default:
		c.JSON(http.StatusOK, response)
	}
}

// handleStats handles GET /api/v1/stats
func (s *Server) handleStats(c *gin.Context) {
	queueLen, err := s.db.GetQueueLength()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get queue length"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"queue_length": queueLen,
	})
}

// handleBuildsPerDay handles GET /api/v1/builds-per-day
func (s *Server) handleBuildsPerDay(c *gin.Context) {
	days := 30 // default
	if d := c.Query("days"); d != "" {
		fmt.Sscanf(d, "%d", &days)
	}

	stats, err := s.db.GetBuildStatsPerDay(days)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get statistics"})
		return
	}

	c.JSON(http.StatusOK, stats)
}

// handleBuildsByVersion handles GET /api/v1/builds-by-version
func (s *Server) handleBuildsByVersion(c *gin.Context) {
	weeks := 26 // default
	if w := c.Query("weeks"); w != "" {
		fmt.Sscanf(w, "%d", &weeks)
	}

	stats, err := s.db.GetBuildStatsByVersion(weeks)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get statistics"})
		return
	}

	c.JSON(http.StatusOK, stats)
}

// handleHealth handles GET /health
func (s *Server) handleHealth(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status": "healthy",
		"time":   time.Now().Unix(),
	})
}
