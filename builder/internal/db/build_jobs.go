package db

import (
	"database/sql"
	"fmt"
	"time"

	"github.com/aparcar/asu/builder/internal/models"
)

// CreateBuildJob inserts a new build job
func (db *DB) CreateBuildJob(job *models.BuildJob) (int64, error) {
	query := `
		INSERT INTO build_jobs (request_hash, status, queue_position)
		VALUES (?, ?, ?)
	`

	result, err := db.Exec(query, job.RequestHash, job.Status, job.QueuePosition)
	if err != nil {
		return 0, fmt.Errorf("failed to insert build job: %w", err)
	}

	id, err := result.LastInsertId()
	if err != nil {
		return 0, fmt.Errorf("failed to get last insert ID: %w", err)
	}

	return id, nil
}

// GetBuildJob retrieves a build job by request hash
func (db *DB) GetBuildJob(requestHash string) (*models.BuildJob, error) {
	query := `
		SELECT id, request_hash, status, started_at, finished_at,
			   build_cmd, manifest, error_message, worker_id, queue_position
		FROM build_jobs
		WHERE request_hash = ?
		ORDER BY id DESC
		LIMIT 1
	`

	var job models.BuildJob
	var startedAt, finishedAt sql.NullTime

	err := db.QueryRow(query, requestHash).Scan(
		&job.ID,
		&job.RequestHash,
		&job.Status,
		&startedAt,
		&finishedAt,
		&job.BuildCmd,
		&job.Manifest,
		&job.ErrorMessage,
		&job.WorkerID,
		&job.QueuePosition,
	)

	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query build job: %w", err)
	}

	if startedAt.Valid {
		job.StartedAt = &startedAt.Time
	}
	if finishedAt.Valid {
		job.FinishedAt = &finishedAt.Time
	}

	return &job, nil
}

// GetPendingJobs retrieves all pending build jobs
func (db *DB) GetPendingJobs() ([]*models.BuildJob, error) {
	query := `
		SELECT id, request_hash, status, started_at, finished_at,
			   build_cmd, manifest, error_message, worker_id, queue_position
		FROM build_jobs
		WHERE status = ?
		ORDER BY id ASC
	`

	rows, err := db.Query(query, models.JobStatusPending)
	if err != nil {
		return nil, fmt.Errorf("failed to query pending jobs: %w", err)
	}
	defer rows.Close()

	var jobs []*models.BuildJob
	for rows.Next() {
		var job models.BuildJob
		var startedAt, finishedAt sql.NullTime

		err := rows.Scan(
			&job.ID,
			&job.RequestHash,
			&job.Status,
			&startedAt,
			&finishedAt,
			&job.BuildCmd,
			&job.Manifest,
			&job.ErrorMessage,
			&job.WorkerID,
			&job.QueuePosition,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan job row: %w", err)
		}

		if startedAt.Valid {
			job.StartedAt = &startedAt.Time
		}
		if finishedAt.Valid {
			job.FinishedAt = &finishedAt.Time
		}

		jobs = append(jobs, &job)
	}

	return jobs, rows.Err()
}

// UpdateJobStatus updates the status of a build job
func (db *DB) UpdateJobStatus(requestHash string, status models.JobStatus) error {
	query := `UPDATE build_jobs SET status = ? WHERE request_hash = ?`
	_, err := db.Exec(query, status, requestHash)
	return err
}

// StartBuildJob marks a job as started
func (db *DB) StartBuildJob(requestHash, workerID string) error {
	query := `
		UPDATE build_jobs
		SET status = ?, started_at = ?, worker_id = ?
		WHERE request_hash = ?
	`

	_, err := db.Exec(query, models.JobStatusBuilding, time.Now(), workerID, requestHash)
	return err
}

// CompleteBuildJob marks a job as completed
func (db *DB) CompleteBuildJob(requestHash, buildCmd, manifest string) error {
	query := `
		UPDATE build_jobs
		SET status = ?, finished_at = ?, build_cmd = ?, manifest = ?
		WHERE request_hash = ?
	`

	_, err := db.Exec(query, models.JobStatusCompleted, time.Now(), buildCmd, manifest, requestHash)
	return err
}

// FailBuildJob marks a job as failed
func (db *DB) FailBuildJob(requestHash, errorMessage string) error {
	query := `
		UPDATE build_jobs
		SET status = ?, finished_at = ?, error_message = ?
		WHERE request_hash = ?
	`

	_, err := db.Exec(query, models.JobStatusFailed, time.Now(), errorMessage, requestHash)
	return err
}

// GetQueueLength returns the number of pending jobs
func (db *DB) GetQueueLength() (int, error) {
	var count int
	err := db.QueryRow("SELECT COUNT(*) FROM build_jobs WHERE status = ?", models.JobStatusPending).Scan(&count)
	return count, err
}

// GetQueuePosition returns the position of a job in the queue
func (db *DB) GetQueuePosition(requestHash string) (int, error) {
	job, err := db.GetBuildJob(requestHash)
	if err != nil {
		return 0, err
	}
	if job == nil {
		return 0, fmt.Errorf("job not found")
	}

	var position int
	query := `
		SELECT COUNT(*) + 1
		FROM build_jobs
		WHERE status = ? AND id < ?
	`
	err = db.QueryRow(query, models.JobStatusPending, job.ID).Scan(&position)
	return position, err
}
