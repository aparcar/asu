from datetime import datetime as dt, timedelta, UTC

from fastapi import APIRouter

from asu.config import settings

router = APIRouter()


DAY_MS = 24 * 60 * 60 * 1000
N_DAYS = 30


def start_stop(duration, interval):
    """Calculate the time series boundaries and bucket values."""

    # "stop" is next midnight to define buckets on exact day boundaries.
    stop = dt.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    stop += timedelta(days=1)
    stop = int(stop.timestamp() * 1000)
    start = stop - duration * interval

    stamps = list(range(start, stop, interval))
    labels = [str(dt.fromtimestamp(stamp // 1000, UTC))[:10] + "Z" for stamp in stamps]

    return start, stop, stamps, labels


@router.get("/builds-per-day")
def get_builds_per_day() -> dict:
    """
    Get builds per day statistics.

    This is a simplified implementation using SQLite.
    TODO: Implement TimeSeries-style aggregation for better performance.
    """
    if not settings.server_stats:
        return {"labels": [], "datasets": []}

    start, stop, stamps, labels = start_stop(N_DAYS, DAY_MS)

    from asu.database import get_session, BuildStats

    session = get_session()
    try:
        # Convert timestamps from milliseconds to datetime
        start_dt = dt.fromtimestamp(start / 1000, UTC)
        stop_dt = dt.fromtimestamp(stop / 1000, UTC)

        # Query stats for each event type
        def get_dataset(event: str, color: str) -> dict:
            """Get dataset for a specific event type."""
            key = f"stats:build:{event}"
            stats = (
                session.query(BuildStats)
                .filter(
                    BuildStats.event_type == key,
                    BuildStats.timestamp >= start_dt,
                    BuildStats.timestamp < stop_dt,
                )
                .all()
            )

            # Group by day
            data_map = {}
            for stat in stats:
                timestamp_ms = int(stat.timestamp.timestamp() * 1000)
                # Align to bucket
                bucket_index = (timestamp_ms - start) // DAY_MS
                bucket_timestamp = start + (bucket_index * DAY_MS)
                data_map[bucket_timestamp] = data_map.get(bucket_timestamp, 0) + 1

            return {
                "label": event.title(),
                "data": [data_map.get(stamp, 0) for stamp in stamps],
                "color": color,
            }

        return {
            "labels": labels,
            "datasets": [
                # See add_build_event for valid "event" values.
                get_dataset("requests", "green"),
                get_dataset("cache-hits", "orange"),
                get_dataset("failures", "red"),
            ],
        }
    finally:
        session.close()


@router.get("/builds-by-version")
def get_builds_by_version(branch: str = None) -> dict:
    """Get builds by version.

    If 'branch' is None, then data will be returned "by branch",
    so you get one curve for each of 23.05, 24.10, 25.12 etc.

    If you specify a branch, say "24.10", then the results are for
    all versions on that branch, 24.10.0, 24.1.1 and so on.

    This is a simplified implementation using SQLite.
    TODO: Implement TimeSeries-style aggregation for better performance.
    """
    if not settings.server_stats:
        return {"labels": [], "datasets": []}

    interval = 7 * DAY_MS  # Each bucket is a week.
    duration = 26  # Number of weeks of data, about 6 months.

    start, stop, stamps, labels = start_stop(duration, interval)

    from asu.database import get_session, BuildStats

    session = get_session()
    try:
        # Convert timestamps from milliseconds to datetime
        start_dt = dt.fromtimestamp(start / 1000, UTC)
        stop_dt = dt.fromtimestamp(stop / 1000, UTC)

        # Query stats for builds
        stats = (
            session.query(BuildStats)
            .filter(
                BuildStats.event_type.like("stats:builds:%"),
                BuildStats.timestamp >= start_dt,
                BuildStats.timestamp < stop_dt,
            )
            .all()
        )

        bucket = {}

        for stat in stats:
            version = stat.event_metadata.get("version", "unknown")

            if branch and not version.startswith(branch):
                continue
            elif branch is None and "." in version:
                version = version[:5]

            if version not in bucket:
                bucket[version] = [0.0] * len(stamps)

            timestamp_ms = int(stat.timestamp.timestamp() * 1000)
            bucket_index = (timestamp_ms - start) // interval

            if 0 <= bucket_index < len(stamps):
                bucket[version][bucket_index] += 1

        return {
            "labels": labels,
            "datasets": [
                {
                    "label": version,
                    "data": bucket[version],
                }
                for version in sorted(bucket)
            ],
        }
    finally:
        session.close()
