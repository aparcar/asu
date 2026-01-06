"""Thread-based job queue implementation to replace RQ.

This module provides Queue and BuildJob classes for managing firmware build jobs
using SQLite and threading.
"""

import logging
import traceback
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime
from typing import Any, Callable, Optional

from asu.database import get_session, Job as JobModel

log = logging.getLogger("asu.worker")


def parse_timeout(timeout_str: str) -> int:
    """Parse timeout string like '10m' or '1h' to seconds.

    Args:
        timeout_str: Timeout string (e.g., '10m', '1h', '30s')

    Returns:
        Timeout in seconds
    """
    if timeout_str is None:
        return None

    timeout_str = str(timeout_str).strip()

    if timeout_str.endswith("s"):
        return int(timeout_str[:-1])
    elif timeout_str.endswith("m"):
        return int(timeout_str[:-1]) * 60
    elif timeout_str.endswith("h"):
        return int(timeout_str[:-1]) * 3600
    elif timeout_str.endswith("d"):
        return int(timeout_str[:-1]) * 86400
    else:
        # Assume it's already in seconds
        return int(timeout_str)


class BuildJob:
    """Represents a firmware build job with simplified state management."""

    def __init__(self, job_id: str):
        """Initialize BuildJob with job ID.

        Args:
            job_id: Unique job identifier
        """
        self.id = job_id
        self._cached_state = None
        self._future: Optional[Future] = None
        self._meta_cache = None  # Cache for meta dict to track modifications

    def get_state(self, refresh: bool = False) -> Optional[dict]:
        """Get full job state in one query.

        Args:
            refresh: Force refresh from database

        Returns:
            dict with keys: id, status, meta, result, enqueued_at, started_at,
            finished_at, exc_string, queue_position (if queued), or None if not found
        """
        if self._cached_state is None or refresh:
            session = get_session()
            try:
                job_model = session.query(JobModel).filter_by(id=self.id).first()
                if not job_model:
                    return None

                state = {
                    "id": job_model.id,
                    "status": job_model.status,
                    "meta": job_model.meta or {},
                    "result": job_model.result,
                    "enqueued_at": job_model.enqueued_at,
                    "started_at": job_model.started_at,
                    "finished_at": job_model.finished_at,
                    "exc_string": job_model.exc_string,
                }

                # Calculate queue position if queued
                if job_model.status == "queued":
                    position = (
                        session.query(JobModel)
                        .filter(
                            JobModel.status == "queued",
                            JobModel.enqueued_at < job_model.enqueued_at,
                        )
                        .count()
                    )
                    state["queue_position"] = position
                else:
                    state["queue_position"] = None

                self._cached_state = state
                self._meta_cache = None  # Invalidate meta cache when state refreshes
            finally:
                session.close()

        return self._cached_state

    def update_meta(self, meta_updates: dict):
        """Update job metadata efficiently.

        Args:
            meta_updates: Dictionary of metadata to update/add
        """
        session = get_session()
        try:
            job_model = session.query(JobModel).filter_by(id=self.id).first()
            if job_model:
                current_meta = dict(job_model.meta or {})
                current_meta.update(meta_updates)
                # Force SQLAlchemy to detect the change by creating a new dict
                job_model.meta = current_meta
                # Mark the attribute as modified to ensure SQLAlchemy detects the change
                from sqlalchemy.orm import attributes
                attributes.flag_modified(job_model, "meta")
                session.commit()
                # Invalidate caches
                self._cached_state = None
                self._meta_cache = None
        finally:
            session.close()

    def update_status(self, status: str, **fields):
        """Update job status and optional fields.

        Args:
            status: New status (queued, started, finished, failed)
            **fields: Additional fields to update (result, exc_string, etc.)
        """
        session = get_session()
        try:
            job_model = session.query(JobModel).filter_by(id=self.id).first()
            if job_model:
                job_model.status = status
                for key, value in fields.items():
                    setattr(job_model, key, value)
                session.commit()
                # Invalidate caches
                self._cached_state = None
                self._meta_cache = None
        finally:
            session.close()

    @property
    def status(self) -> Optional[str]:
        """Get current job status."""
        state = self.get_state()
        return state["status"] if state else None

    @property
    def meta(self) -> dict:
        """Get job metadata.
        
        Returns a dict that can be modified. Call save_meta() to persist changes.
        """
        if self._meta_cache is None:
            state = self.get_state()
            if state:
                # Create a copy so modifications don't affect cached state
                self._meta_cache = dict(state["meta"])
            else:
                self._meta_cache = {}
        return self._meta_cache

    @meta.setter
    def meta(self, value: dict) -> None:
        """Set job metadata.

        Args:
            value: Metadata dictionary to set (replaces all existing metadata)
        """
        session = get_session()
        try:
            job_model = session.query(JobModel).filter_by(id=self.id).first()
            if job_model:
                job_model.meta = value
                session.commit()
                # Invalidate caches
                self._cached_state = None
                self._meta_cache = None
        finally:
            session.close()

    def save_meta(self) -> None:
        """Save current metadata to database.
        
        This persists any modifications made to the dict returned by the meta property.
        """
        if self._meta_cache is not None:
            # Save the modified meta cache
            self.meta = self._meta_cache

    @property
    def enqueued_at(self) -> Optional[datetime]:
        """Get when the job was enqueued."""
        state = self.get_state()
        return state["enqueued_at"] if state else None


class Queue:
    """Queue class that mimics RQ's Queue interface.

    This class manages job submission and execution using a ThreadPoolExecutor.
    """

    def __init__(self, max_workers: int = 4, is_async: bool = True):
        """Initialize Queue.

        Args:
            max_workers: Maximum number of worker threads
            is_async: Whether to execute jobs asynchronously
        """
        self.max_workers = max_workers
        self.is_async = is_async
        self._executor = (
            ThreadPoolExecutor(max_workers=max_workers) if is_async else None
        )
        log.info(f"Queue initialized with {max_workers} workers (async={is_async})")

    def enqueue(
        self,
        func: Callable,
        *args,
        job_id: Optional[str] = None,
        result_ttl: Optional[str] = None,
        failure_ttl: Optional[str] = None,
        job_timeout: Optional[str] = None,
        **kwargs,
    ) -> BuildJob:
        """Enqueue a job for execution.

        Args:
            func: Function to execute
            args: Positional arguments for function
            job_id: Unique job ID
            result_ttl: Time to keep successful results
            failure_ttl: Time to keep failed results
            job_timeout: Job execution timeout
            kwargs: Keyword arguments for function

        Returns:
            BuildJob object
        """
        if not job_id:
            import uuid

            job_id = str(uuid.uuid4())

        # Parse TTL values
        result_ttl_seconds = parse_timeout(result_ttl) if result_ttl else None
        failure_ttl_seconds = parse_timeout(failure_ttl) if failure_ttl else None

        # Create job in database
        session = get_session()
        try:
            job_model = JobModel(
                id=job_id,
                status="queued",
                meta={},
                result_ttl=result_ttl_seconds,
                failure_ttl=failure_ttl_seconds,
            )
            session.add(job_model)
            session.commit()
        finally:
            session.close()

        job = BuildJob(job_id)

        # Execute job
        if self.is_async:
            future = self._executor.submit(
                self._execute_job, job_id, func, args, kwargs
            )
            job._future = future
        else:
            # Synchronous execution for testing
            self._execute_job(job_id, func, args, kwargs)

        return job

    def _execute_job(
        self, job_id: str, func: Callable, args: tuple, kwargs: dict
    ) -> None:
        """Execute a job.

        Args:
            job_id: Job ID
            func: Function to execute
            args: Positional arguments
            kwargs: Keyword arguments
        """
        session = get_session()
        try:
            # Update job status to started
            job_model = session.query(JobModel).filter_by(id=job_id).first()
            if not job_model:
                log.error(f"Job {job_id} not found in database")
                return

            job_model.status = "started"
            job_model.started_at = datetime.utcnow()
            session.commit()
            session.close()

            # Create Job wrapper to pass to function
            job_wrapper = BuildJob(job_id)

            # Execute function
            try:
                log.info(f"Starting job {job_id}")
                result = func(*args, job=job_wrapper, **kwargs)

                # Update job with result
                session = get_session()
                job_model = session.query(JobModel).filter_by(id=job_id).first()
                if job_model:
                    job_model.status = "finished"
                    job_model.result = result
                    job_model.finished_at = datetime.utcnow()
                    session.commit()
                log.info(f"Job {job_id} completed successfully")

            except Exception as e:
                log.error(f"Job {job_id} failed: {e}", exc_info=True)
                # Update job with error
                session = get_session()
                job_model = session.query(JobModel).filter_by(id=job_id).first()
                if job_model:
                    job_model.status = "failed"
                    job_model.exc_string = traceback.format_exc()
                    job_model.finished_at = datetime.utcnow()
                    session.commit()

        finally:
            if session:
                session.close()

    def fetch_job(self, job_id: str) -> Optional[BuildJob]:
        """Fetch a job by ID.

        Args:
            job_id: Job ID

        Returns:
            BuildJob object or None
        """
        session = get_session()
        try:
            job_model = session.query(JobModel).filter_by(id=job_id).first()
            if job_model:
                return BuildJob(job_id)
            return None
        finally:
            session.close()

    def __len__(self) -> int:
        """Get number of queued jobs.

        Returns:
            Number of queued jobs
        """
        session = get_session()
        try:
            return session.query(JobModel).filter_by(status="queued").count()
        finally:
            session.close()

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the queue and thread pool.

        Args:
            wait: Whether to wait for running jobs to complete
        """
        if self._executor:
            log.info("Shutting down job queue...")
            self._executor.shutdown(wait=wait)
            log.info("Job queue shutdown complete")


# Global queue instance
_queue: Optional[Queue] = None


def init_queue(max_workers: int = 4, is_async: bool = True) -> Queue:
    """Initialize the global queue.

    Args:
        max_workers: Maximum number of worker threads
        is_async: Whether to execute jobs asynchronously

    Returns:
        Queue instance
    """
    global _queue
    _queue = Queue(max_workers=max_workers, is_async=is_async)
    return _queue


def get_queue() -> Queue:
    """Get the global queue instance.

    Returns:
        Queue instance
    """
    if _queue is None:
        raise RuntimeError("Queue not initialized. Call init_queue() first.")
    return _queue


def shutdown_queue(wait: bool = True) -> None:
    """Shutdown the global queue.

    Args:
        wait: Whether to wait for running jobs to complete
    """
    global _queue
    if _queue:
        _queue.shutdown(wait=wait)
        _queue = None
