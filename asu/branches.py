import json
import logging
from pathlib import Path

import jsonschema
import yaml

log = logging.getLogger("rq.worker")

_schema_path = Path(__file__).resolve().parent.parent / "asu_schema.json"
_schema = json.loads(_schema_path.read_text())

_DEFAULTS = {
    "path": "releases/{version}",
    "enabled": True,
    "snapshot": False,
}

# --- Mtime-based auto-reload cache ---

_cached_branches: dict[str, dict] | None = None
_cached_mtime: float = 0
_cached_path: Path | None = None

# Optional overrides injected by tests (branch_name -> dict).
_overrides: dict[str, dict] = {}


def _load_branches(path: Path | None = None) -> dict[str, dict]:
    global _cached_branches, _cached_mtime, _cached_path

    if path is None:
        from asu.config import settings

        path = settings.openwrt_config_file

    path = Path(path)
    mtime = path.stat().st_mtime

    if path == _cached_path and mtime == _cached_mtime and _cached_branches is not None:
        return _cached_branches

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    jsonschema.validate(raw, _schema)

    branches: dict[str, dict] = {}
    for name, data in (raw.get("branches") or {}).items():
        # YAML parses numeric-looking keys (e.g. 24.10) as floats;
        # coerce all branch names to strings.
        name = str(name)
        branch = {**_DEFAULTS, **(data or {})}
        branches[name] = branch

    _cached_branches = branches
    _cached_mtime = mtime
    _cached_path = path
    log.debug(f"Loaded branch definitions from {path}")

    return _cached_branches


def get_branches() -> dict[str, dict]:
    """Return all branch definitions, auto-reloading from YAML on change.

    Any overrides added via ``set_branch_override`` are merged on top.
    """
    branches = dict(_load_branches())
    if _overrides:
        branches.update(_overrides)
    return branches


def set_branch_override(name: str, data: dict) -> None:
    """Add a branch override (used by tests to inject extra branches)."""
    _overrides[name] = data


def clear_branch_overrides() -> None:
    """Remove all branch overrides."""
    _overrides.clear()
