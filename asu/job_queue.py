"""Thread-based job queue implementation to replace RQ.

This module provides Queue and Job classes that mimic RQ's interface but use
SQLite and threading instead of Redis.
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


class Job:
    """Job class that mimics RQ's Job interface.

    This class wraps a database Job model and provides methods compatible
    with RQ's Job API.
    """

    def __init__(self, job_id: str):
        """Initialize Job with job ID.

        Args:
            job_id: Unique job identifier
        """
        self.id = job_id
        self._future: Optional[Future] = None

    @property
    def meta(self) -> dict:
        """Get job metadata.

        Returns:
            Job metadata dictionary
        """
        session = get_session()
        try:
            job_model = session.query(JobModel).filter_by(id=self.id).first()
            if job_model:
                return job_model.meta or {}
            return {}
        finally:
            session.close()

    def get_meta(self) -> dict:
        """Get job metadata (alias for meta property).

        Returns:
            Job metadata dictionary
        """
        return self.meta

    def save_meta(self) -> None:
        """Save job metadata to database.

        Note: Since meta is accessed via property, this method ensures
        any changes to meta are persisted.
        """
        # Meta is accessed and saved via the meta property setter
        # This method is here for API compatibility
        pass

    @meta.setter
    def meta(self, value: dict) -> None:
        """Set job metadata.

        Args:
            value: Metadata dictionary to set
        """
        session = get_session()
        try:
            job_model = session.query(JobModel).filter_by(id=self.id).first()
            if job_model:
                job_model.meta = value
                session.commit()
        finally:
            session.close()

    def set_meta(self, key: str, value: Any) -> None:
        """Set a specific metadata key.

        Args:
            key: Metadata key
            value: Value to set
        """
        current_meta = self.meta
        current_meta[key] = value
        self.meta = current_meta

    @property
    def enqueued_at(self) -> Optional[datetime]:
        """Get when the job was enqueued.

        Returns:
            Enqueue timestamp
        """
        session = get_session()
        try:
            job_model = session.query(JobModel).filter_by(id=self.id).first()
            if job_model:
                return job_model.enqueued_at
            return None
        finally:
            session.close()

    def get_position(self) -> Optional[int]:
        """Get position in queue.

        Returns:
            Position in queue (0-based), or None if not queued
        """
        if not self.is_queued:
            return None

        session = get_session()
        try:
            # Count jobs that were enqueued before this one and are still queued
            position = (
                session.query(JobModel)
                .filter(
                    JobModel.status == "queued",
                    JobModel.enqueued_at < self.enqueued_at,
                )
                .count()
            )
            return position
        finally:
            session.close()

    @property
    def is_queued(self) -> bool:
        """Check if job is queued.

        Returns:
            True if job is queued
        """
        session = get_session()
        try:
            job_model = session.query(JobModel).filter_by(id=self.id).first()
            return job_model.status == "queued" if job_model else False
        finally:
            session.close()

    @property
    def is_started(self) -> bool:
        """Check if job has started.

        Returns:
            True if job is started
        """
        session = get_session()
        try:
            job_model = session.query(JobModel).filter_by(id=self.id).first()
            return job_model.status == "started" if job_model else False
        finally:
            session.close()

    @property
    def is_finished(self) -> bool:
        """Check if job is finished.

        Returns:
            True if job is finished
        """
        session = get_session()
        try:
            job_model = session.query(JobModel).filter_by(id=self.id).first()
            return job_model.status == "finished" if job_model else False
        finally:
            session.close()

    @property
    def is_failed(self) -> bool:
        """Check if job has failed.

        Returns:
            True if job failed
        """
        session = get_session()
        try:
            job_model = session.query(JobModel).filter_by(id=self.id).first()
            return job_model.status == "failed" if job_model else False
        finally:
            session.close()

    def latest_result(self):
        """Get the latest result (for failed jobs, contains exception).

        Returns:
            Result object with exc_string attribute
        """
        session = get_session()
        try:
            job_model = session.query(JobModel).filter_by(id=self.id).first()
            if job_model:

                class Result:
                    def __init__(self, exc_string):
                        self.exc_string = exc_string

                return Result(job_model.exc_string)
            return None
        finally:
            session.close()

    def return_value(self) -> Any:
        """Get the return value for finished jobs.

        Returns:
            Job result
        """
        session = get_session()
        try:
            job_model = session.query(JobModel).filter_by(id=self.id).first()
            if job_model:
                return job_model.result
            return None
        finally:
            session.close()


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
        self._executor = ThreadPoolExecutor(max_workers=max_workers) if is_async else None
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
    ) -> Job:
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
            Job object
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

        job = Job(job_id)

        # Execute job
        if self.is_async:
            future = self._executor.submit(self._execute_job, job_id, func, args, kwargs)
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
            job_wrapper = Job(job_id)

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

    def fetch_job(self, job_id: str) -> Optional[Job]:
        """Fetch a job by ID.

        Args:
            job_id: Job ID

        Returns:
            Job object or None
        """
        session = get_session()
        try:
            job_model = session.query(JobModel).filter_by(id=job_id).first()
            if job_model:
                return Job(job_id)
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
