package api

import (
	"fmt"
	"html/template"
	"io/fs"
	"net/http"

	"github.com/aparcar/asu/builder/internal/config"
	"github.com/aparcar/asu/builder/internal/web"
	"github.com/gin-gonic/gin"
)

// setupWebRoutes configures the web UI routes
func (s *Server) setupWebRoutes() {
	// Serve static files
	staticFS, err := fs.Sub(web.StaticFS, "static")
	if err != nil {
		panic(fmt.Sprintf("Failed to get static FS: %v", err))
	}
	s.router.StaticFS("/static", http.FS(staticFS))

	// Web UI routes
	s.router.GET("/", s.handleOverviewPage)
	s.router.GET("/status", s.handleStatusPage)
	s.router.GET("/stats", s.handleStatsPage)
	s.router.GET("/config", s.handleConfigPage)
}

// PageData holds common data for all pages
type PageData struct {
	Title  string
	Active string
	Config *config.Config
}

// renderTemplate renders an HTML template
func (s *Server) renderTemplate(c *gin.Context, templateName string, data PageData) {
	// Parse templates
	tmpl, err := template.New("").Funcs(template.FuncMap{
		"formatDuration": formatDuration,
	}).ParseFS(web.TemplatesFS, "templates/*.html")

	if err != nil {
		c.String(http.StatusInternalServerError, "Template parsing error: %v", err)
		return
	}

	c.Header("Content-Type", "text/html; charset=utf-8")
	c.Status(http.StatusOK)

	err = tmpl.ExecuteTemplate(c.Writer, templateName, data)
	if err != nil {
		c.String(http.StatusInternalServerError, "Template execution error: %v", err)
	}
}

// handleOverviewPage renders the overview dashboard
func (s *Server) handleOverviewPage(c *gin.Context) {
	data := PageData{
		Title:  "Overview",
		Active: "overview",
		Config: s.config,
	}
	s.renderTemplate(c, "layout.html", data)
}

// handleStatusPage renders the status page
func (s *Server) handleStatusPage(c *gin.Context) {
	data := PageData{
		Title:  "Status",
		Active: "status",
		Config: s.config,
	}
	s.renderTemplate(c, "layout.html", data)
}

// handleStatsPage renders the statistics page
func (s *Server) handleStatsPage(c *gin.Context) {
	data := PageData{
		Title:  "Statistics",
		Active: "stats",
		Config: s.config,
	}
	s.renderTemplate(c, "layout.html", data)
}

// handleConfigPage renders the configuration page
func (s *Server) handleConfigPage(c *gin.Context) {
	data := PageData{
		Title:  "Configuration",
		Active: "config",
		Config: s.config,
	}
	s.renderTemplate(c, "layout.html", data)
}

// formatDuration formats seconds into human-readable duration
func formatDuration(seconds int) string {
	if seconds < 60 {
		return fmt.Sprintf("%ds", seconds)
	}
	if seconds < 3600 {
		return fmt.Sprintf("%dm", seconds/60)
	}
	if seconds < 86400 {
		return fmt.Sprintf("%dh", seconds/3600)
	}
	return fmt.Sprintf("%dd", seconds/86400)
}
