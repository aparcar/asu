from datetime import datetime as dt, timedelta, UTC

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from asu.util import error_log, get_redis_ts

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
    References:
    https://redis.readthedocs.io/en/latest/redismodules.html#redis.commands.timeseries.commands.TimeSeriesCommands.range
    https://www.chartjs.org/docs/latest/charts/line.html
    """

    start, stop, stamps, labels = start_stop(N_DAYS, DAY_MS)

    ts = get_redis_ts()
    rc = ts.client
    range_options = dict(
        from_time=start,
        to_time=stop,
        align=start,  # Ensures alignment of X values with "stamps".
        aggregation_type="sum",
        bucket_size_msec=DAY_MS,
    )

    def get_dataset(event: str, color: str) -> dict:
        """Fills "data" array completely, supplying 0 for missing values."""
        key = f"stats:build:{event}"
        result = ts.range(key, **range_options) if rc.exists(key) else []
        data_map = dict(result)
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


@router.get("/builds-by-version")
def get_builds_by_version(branch: str = None) -> dict():
    """If 'branch' is None, then data will be returned "by branch",
    so you get one curve for each of 23.05, 24.10, 25.12 etc.

    If you specify a branch, say "24.10", then the results are for
    all versions on that branch, 24.10.0, 24.1.1 and so on."""

    interval = 7 * DAY_MS  # Each bucket is a week.
    duration = 26  # Number of weeks of data, about 6 months.

    start, stop, stamps, labels = start_stop(duration, interval)

    bucket = {}

    def sum_data(version, data):
        data_map = dict(data)
        if version not in bucket:
            bucket[version] = [0.0] * len(stamps)
        for i, stamp in enumerate(stamps):
            bucket[version][i] += data_map.get(stamp, 0)

    range_options = dict(
        filters=["stats=builds"],
        with_labels=True,
        from_time=start,
        to_time=stop,
        align=start,  # Ensures alignment of X values with "stamps".
        aggregation_type="sum",
        bucket_size_msec=interval,
    )

    result = get_redis_ts().mrange(**range_options)
    for row in result:
        for data in row.values():
            version = data[0]["version"]
            if branch and not version.startswith(branch):
                continue
            elif branch is None and "." in version:
                version = version[:5]
            sum_data(version, data[1])

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


@router.get("/build-errors", response_class=PlainTextResponse)
def get_build_errors(n: int = 100) -> str:
    """Return a summary of recent build errors.

    Args:
        n: Maximum number of entries to return (default 100, max 500)

    Returns:
        Plain text summary of build errors
    """
    return error_log.get_summary(min(n, 500))
