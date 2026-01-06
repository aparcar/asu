"""Database module for ASU using SQLAlchemy.

This module provides SQLAlchemy models and database utilities for managing
build jobs and statistics without requiring Redis.
"""

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    String,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker

log = logging.getLogger("asu.worker")

Base = declarative_base()


class Job(Base):
    """Model for storing job information."""

    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    status = Column(String, default="queued")  # queued, started, finished, failed
    meta = Column(JSON, default=dict)
    result = Column(JSON, nullable=True)
    enqueued_at = Column(DateTime, default=lambda: datetime.now(UTC))
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    failure_ttl = Column(Integer, nullable=True)  # in seconds
    result_ttl = Column(Integer, nullable=True)  # in seconds
    exc_string = Column(String, nullable=True)  # Exception string for failed jobs

    def __repr__(self):
        return f"<Job(id={self.id}, status={self.status})>"


class BuildStats(Base):
    """Model for storing build statistics."""

    __tablename__ = "build_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(UTC), index=True)
    event_metadata = Column(JSON, default=dict)

    def __repr__(self):
        return f"<BuildStats(event_type={self.event_type}, timestamp={self.timestamp})>"


# Global session factory
_session_factory = None
_engine = None


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable SQLite optimizations for multi-threaded use."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
    cursor.close()


def init_database(database_path: Path) -> None:
    """Initialize the database and create tables.

    Args:
        database_path: Path to the SQLite database file
    """
    global _session_factory, _engine

    database_path.parent.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{database_path}"

    _engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )

    Base.metadata.create_all(_engine)

    _session_factory = scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    )

    log.info(f"Database initialized at {database_path}")


def get_session():
    """Get a database session.

    Returns:
        SQLAlchemy session
    """
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _session_factory()


def cleanup_expired_jobs() -> int:
    """Remove expired jobs from the database.

    Returns:
        Number of jobs removed
    """
    session = get_session()
    try:
        now = datetime.now(UTC)
        expired_count = 0

        # Find expired finished jobs
        finished_jobs = (
            session.query(Job)
            .filter(Job.status == "finished", Job.result_ttl.isnot(None))
            .all()
        )

        for job in finished_jobs:
            if job.finished_at:
                expiry_time = job.finished_at + timedelta(seconds=job.result_ttl)
                if now > expiry_time:
                    session.delete(job)
                    expired_count += 1

        # Find expired failed jobs
        failed_jobs = (
            session.query(Job)
            .filter(Job.status == "failed", Job.failure_ttl.isnot(None))
            .all()
        )

        for job in failed_jobs:
            if job.finished_at:
                expiry_time = job.finished_at + timedelta(seconds=job.failure_ttl)
                if now > expiry_time:
                    session.delete(job)
                    expired_count += 1

        session.commit()
        return expired_count
    finally:
        session.close()


def close_database() -> None:
    """Close database connections."""
    global _session_factory, _engine

    if _session_factory:
        _session_factory.remove()
        _session_factory = None

    if _engine:
        _engine.dispose()
        _engine = None

    log.info("Database connections closed")
