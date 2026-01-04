#!/usr/bin/env python3
"""Package Changes Service - Handles OpenWrt package transformations."""

import logging
import re
import time
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Set

import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TransformRequest(BaseModel):
    """Package transformation request."""
    from_version: Optional[str] = None
    version: str
    target: str
    profile: str
    packages: List[str]
    default_packages: List[str] = []
    diff_packages: bool = False


class TransformResponse(BaseModel):
    """Package transformation response."""
    packages: List[str]
    warnings: List[str] = []
    applied: List[str] = []


class ConfigReloader(FileSystemEventHandler):
    """Watches config file and reloads on changes."""

    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.last_reload = 0

    def on_modified(self, event):
        if event.src_path.endswith('.yaml'):
            # Debounce rapid file changes
            current_time = time.time()
            if current_time - self.last_reload < 1.0:
                return

            logger.info(f"Config file modified: {event.src_path}")
            self.config_manager.reload_config()
            self.last_reload = current_time


class ConfigManager:
    """Manages configuration with hot reload."""

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.config: Dict = {}
        self.lock = Lock()
        self.load_config()

        # Setup file watcher
        self.observer = Observer()
        handler = ConfigReloader(self)
        self.observer.schedule(handler, str(self.config_path.parent), recursive=False)
        self.observer.start()
        logger.info(f"Watching config file: {self.config_path}")

    def load_config(self):
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, 'r') as f:
                new_config = yaml.safe_load(f)

            with self.lock:
                self.config = new_config

            logger.info(f"Configuration loaded from {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise

    def reload_config(self):
        """Reload configuration."""
        try:
            self.load_config()
            logger.info("Configuration reloaded successfully")
        except Exception as e:
            logger.error(f"Failed to reload config: {e}")

    def get_config(self) -> Dict:
        """Get current configuration (thread-safe)."""
        with self.lock:
            return self.config.copy()


class PackageTransformer:
    """Transforms package lists based on configuration rules."""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager

    def transform(self, req: TransformRequest) -> TransformResponse:
        """Apply all transformations to package list."""
        config = self.config_manager.get_config()

        packages = set(req.packages)
        warnings = []
        applied = []

        # 1. Apply version transition if from_version specified
        if req.from_version and req.from_version != req.version:
            packages, trans_applied = self._apply_version_transition(
                packages, req.from_version, req.version, config
            )
            applied.extend(trans_applied)

        # 2. Apply package renames
        packages, rename_applied = self._apply_package_renames(
            packages, req.version, config
        )
        applied.extend(rename_applied)

        # 3. Check for deprecated packages
        pkg_warnings = self._check_deprecated(packages, req.version, config)
        warnings.extend(pkg_warnings)

        # 4. Apply custom rules
        packages, custom_applied = self._apply_custom_rules(
            packages, req.version, config
        )
        applied.extend(custom_applied)

        # 5. Apply profile-specific additions
        packages, profile_applied = self._apply_profile_specific(
            packages, req.profile, config
        )
        applied.extend(profile_applied)

        # 6. Apply conflict resolution
        packages, conflict_applied = self._resolve_conflicts(packages, config)
        applied.extend(conflict_applied)

        return TransformResponse(
            packages=sorted(list(packages)),
            warnings=warnings,
            applied=applied
        )

    def _apply_version_transition(
        self, packages: Set[str], from_version: str, to_version: str, config: Dict
    ) -> tuple[Set[str], List[str]]:
        """Apply version transition rules."""
        applied = []
        transitions = config.get('version_transitions', {})
        key = f"{from_version}->{to_version}"

        if key not in transitions:
            return packages, applied

        trans = transitions[key]

        # Remove packages
        for pkg in trans.get('remove', []):
            if pkg in packages:
                packages.remove(pkg)
                applied.append(f"version_transition: removed {pkg}")

        # Add packages
        for pkg in trans.get('add', []):
            if pkg not in packages:
                packages.add(pkg)
                applied.append(f"version_transition: added {pkg}")

        # Replace packages
        for old, new in trans.get('replace', {}).items():
            if old in packages:
                packages.remove(old)
                packages.add(new)
                applied.append(f"version_transition: replaced {old} -> {new}")

        return packages, applied

    def _apply_package_renames(
        self, packages: Set[str], version: str, config: Dict
    ) -> tuple[Set[str], List[str]]:
        """Apply version-specific package renames."""
        applied = []
        renames = config.get('package_renames', {}).get(version, {})

        for old, new in renames.items():
            if old in packages:
                packages.remove(old)
                packages.add(new)
                applied.append(f"rename: {old} -> {new}")
                logger.info(f"Renamed package: {old} -> {new}")

        return packages, applied

    def _check_deprecated(
        self, packages: Set[str], version: str, config: Dict
    ) -> List[str]:
        """Check for deprecated packages and return warnings."""
        warnings = []
        deprecated = config.get('deprecated_packages', {})

        for pkg in packages:
            if pkg in deprecated:
                dep_info = deprecated[pkg]
                if self._version_gte(version, dep_info.get('since', '0.0')):
                    warnings.append(dep_info.get('warning', f"{pkg} is deprecated"))

        return warnings

    def _apply_custom_rules(
        self, packages: Set[str], version: str, config: Dict
    ) -> tuple[Set[str], List[str]]:
        """Apply custom transformation rules."""
        applied = []
        rules = config.get('custom_rules', {}).get(version, {})

        for rule_name, rule_data in rules.items():
            for transform in rule_data.get('transforms', []):
                if_contains = transform.get('if_contains')

                if if_contains and if_contains in packages:
                    # Add package
                    if 'add' in transform and transform['add'] not in packages:
                        packages.add(transform['add'])
                        applied.append(f"custom_rule({rule_name}): added {transform['add']}")

                    # Remove package
                    if 'remove' in transform and transform['remove'] in packages:
                        packages.remove(transform['remove'])
                        applied.append(f"custom_rule({rule_name}): removed {transform['remove']}")

        return packages, applied

    def _apply_profile_specific(
        self, packages: Set[str], profile: str, config: Dict
    ) -> tuple[Set[str], List[str]]:
        """Apply profile-specific package additions."""
        applied = []
        profile_pkgs = config.get('profile_specific', {}).get(profile, [])

        for pkg in profile_pkgs:
            if pkg not in packages:
                packages.add(pkg)
                applied.append(f"profile_specific: added {pkg}")

        return packages, applied

    def _resolve_conflicts(
        self, packages: Set[str], config: Dict
    ) -> tuple[Set[str], List[str]]:
        """Resolve package conflicts."""
        applied = []
        conflicts = config.get('conflicts', {})

        for pkg, conflict_info in conflicts.items():
            if pkg in packages:
                for conflicting in conflict_info.get('conflicts_with', []):
                    if conflicting in packages:
                        action = conflict_info.get('action')
                        if action == 'remove_conflicting':
                            packages.remove(conflicting)
                            applied.append(f"conflict: removed {conflicting} (conflicts with {pkg})")

        return packages, applied

    @staticmethod
    def _version_gte(v1: str, v2: str) -> bool:
        """Simple version comparison (greater than or equal)."""
        return v1 >= v2  # String comparison works for semantic versions


# Create FastAPI app
app = FastAPI(
    title="Package Changes Service",
    description="OpenWrt package transformation service",
    version="1.0.0"
)

# Initialize config manager and transformer
config_manager = ConfigManager("package_changes.yaml")
transformer = PackageTransformer(config_manager)


@app.post("/apply", response_model=TransformResponse)
async def apply_changes(request: TransformRequest):
    """Apply package transformations."""
    try:
        return transformer.transform(request)
    except Exception as e:
        logger.error(f"Transformation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "config_file": str(config_manager.config_path)
    }


@app.post("/reload")
async def reload_config():
    """Manually reload configuration."""
    try:
        config_manager.reload_config()
        return {"status": "configuration reloaded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
