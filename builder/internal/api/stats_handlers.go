package api

import (
	"fmt"
	"net/http"

	"github.com/gin-gonic/gin"
)

// handleDiffPackagesStats handles GET /api/v1/diff-packages-stats
func (s *Server) handleDiffPackagesStats(c *gin.Context) {
	days := 30 // default
	if d := c.Query("days"); d != "" {
		fmt.Sscanf(d, "%d", &days)
	}

	stats, err := s.db.GetDiffPackagesStats(days)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get diff_packages statistics"})
		return
	}

	c.JSON(http.StatusOK, stats)
}

// handleDiffPackagesByVersion handles GET /api/v1/diff-packages-by-version
func (s *Server) handleDiffPackagesByVersion(c *gin.Context) {
	weeks := 26 // default
	if w := c.Query("weeks"); w != "" {
		fmt.Sscanf(w, "%d", &weeks)
	}

	stats, err := s.db.GetDiffPackagesStatsByVersion(weeks)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get diff_packages statistics by version"})
		return
	}

	c.JSON(http.StatusOK, stats)
}

// handleDiffPackagesTrend handles GET /api/v1/diff-packages-trend
func (s *Server) handleDiffPackagesTrend(c *gin.Context) {
	days := 30 // default
	if d := c.Query("days"); d != "" {
		fmt.Sscanf(d, "%d", &days)
	}

	trend, err := s.db.GetDiffPackagesTrend(days)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get diff_packages trend"})
		return
	}

	c.JSON(http.StatusOK, trend)
}
