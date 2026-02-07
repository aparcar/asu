import json
import logging
from pathlib import Path

import jsonschema
import yaml

from asu.build_request import BuildRequest

log = logging.getLogger("rq.worker")

_schema_path = Path(__file__).resolve().parent.parent / "asu_schema.json"
_schema = json.loads(_schema_path.read_text())

# --- Mtime-based auto-reload cache ---

_cached_data: dict | None = None
_cached_mtime: float = 0
_cached_path: Path | None = None


def _load_package_changes(path: Path | None = None) -> dict:
    global _cached_data, _cached_mtime, _cached_path

    if path is None:
        from asu.config import settings

        path = settings.openwrt_config_file

    path = Path(path)
    mtime = path.stat().st_mtime

    if path == _cached_path and mtime == _cached_mtime and _cached_data is not None:
        return _cached_data

    with open(path) as f:
        raw = yaml.safe_load(f)

    jsonschema.validate(raw, _schema)

    _cached_data = raw
    _cached_mtime = mtime
    _cached_path = path
    log.debug(f"Loaded package changes from {path}")

    return _cached_data


def get_revision_changes(before: int | None = None) -> list[dict]:
    """Return revision-based package changes, optionally filtered by revision.

    This replaces the old ``package_changes()`` function from config.py.
    Results are serialised as plain dicts for JSON API responses.
    """
    data = _load_package_changes()
    changes = []
    for rc in data["revision_changes"]:
        if before is None or rc["revision"] <= before:
            entry: dict = {"revision": rc["revision"]}
            if "source" in rc:
                entry["source"] = rc["source"]
            if "target" in rc:
                entry["target"] = rc["target"]
            if rc.get("mandatory"):
                entry["mandatory"] = rc["mandatory"]
            changes.append(entry)
    return changes


# --- Build-time package mutations ---


def apply_package_changes(build_request: BuildRequest) -> None:
    """Apply package changes to the request.

    Reads rules from the YAML file (auto-reloaded on change).
    """
    data = _load_package_changes()

    def _add_if_missing(package: str) -> None:
        if package not in build_request.packages:
            build_request.packages.append(package)
            log.debug(f"Added {package} to packages")

    def _remove_if_present(package: str) -> bool:
        if package in build_request.packages:
            build_request.packages.remove(package)
            log.debug(f"Removed {package} from packages")
            return True
        return False

    # Apply version/target/profile rules
    for vc in data["version_changes"]:
        version = vc["version"]
        if version == "SNAPSHOT":
            version_match = build_request.version == "SNAPSHOT"
        else:
            version_match = build_request.version.startswith(version)

        if not version_match:
            continue

        for rule in vc["rules"]:
            # Replace rules (not scoped to target)
            if "replace" in rule:
                for old_pkg, new_pkg in rule["replace"].items():
                    if _remove_if_present(old_pkg):
                        _add_if_missing(new_pkg)

            # Remove rules (not scoped to target)
            if "remove" in rule and "target" not in rule and "targets" not in rule:
                for pkg in rule["remove"]:
                    _remove_if_present(pkg)

            # Target-scoped rules
            target_match = False
            if "target" in rule and build_request.target == rule["target"]:
                target_match = True
            elif "targets" in rule and build_request.target in rule["targets"]:
                target_match = True

            if target_match and "add" in rule:
                for pkg in rule["add"]:
                    _add_if_missing(pkg)

            if target_match and "remove" in rule:
                for pkg in rule["remove"]:
                    _remove_if_present(pkg)

            # Profile-scoped rules (may or may not require target match)
            if "profiles" in rule:
                # If a target is specified, only apply profiles when target matches
                if ("target" in rule or "targets" in rule) and not target_match:
                    continue
                for profile_rule in rule["profiles"]:
                    if build_request.profile in profile_rule["names"]:
                        for pkg in profile_rule["add"]:
                            _add_if_missing(pkg)

    # Apply language pack replacements
    for lp in data["language_packs"]:
        if build_request.version >= lp["min_version"]:
            for i, package in enumerate(build_request.packages):
                for old_prefix, new_prefix in lp["replacements"].items():
                    if package.startswith(old_prefix):
                        lang = package.removeprefix(old_prefix)
                        build_request.packages[i] = f"{new_prefix}{lang}"
