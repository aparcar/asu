"""
Package resolution logic

This module handles:
- Applying package changes based on version/target/profile
- Tracking what changes were made
- Calculating final package lists for prepare endpoint
"""

import logging
from typing import Optional
from copy import deepcopy

from asu.build_request import BuildRequest
from asu.package_changes import apply_package_changes

log = logging.getLogger("rq.worker")


class PackageChange:
    """Represents a single package change"""

    def __init__(
        self,
        change_type: str,  # migration, addition, removal
        action: str,  # replace, add, remove
        package: Optional[str] = None,
        from_package: Optional[str] = None,
        to_package: Optional[str] = None,
        reason: str = "",
        automatic: bool = True,
    ):
        self.type = change_type
        self.action = action
        self.package = package
        self.from_package = from_package
        self.to_package = to_package
        self.reason = reason
        self.automatic = automatic

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        result = {
            "type": self.type,
            "action": self.action,
            "reason": self.reason,
            "automatic": self.automatic,
        }

        if self.package:
            result["package"] = self.package
        if self.from_package:
            result["from_package"] = self.from_package
        if self.to_package:
            result["to_package"] = self.to_package

        return result


class PackageResolver:
    """Resolves packages for a build request"""

    def __init__(self):
        self.changes: list[PackageChange] = []

    def resolve(
        self, build_request: BuildRequest
    ) -> tuple[list[str], list[PackageChange]]:
        """
        Resolve packages for a build request.

        This method applies package changes based on version/target/profile
        and tracks what was changed.

        Args:
            build_request: The build request to resolve packages for

        Returns:
            Tuple of (final_packages, changes_applied)
        """
        self.changes = []

        # Make a deep copy to track changes
        original_packages = build_request.packages.copy()

        # Apply package changes (existing logic from package_changes.py)
        apply_package_changes(build_request)

        # Track what changed
        self._track_changes(original_packages, build_request.packages, build_request)

        return build_request.packages, self.changes

    def _track_changes(
        self,
        original: list[str],
        modified: list[str],
        build_request: BuildRequest,
    ):
        """Track what changes were made"""
        original_set = set(original)
        modified_set = set(modified)

        added = modified_set - original_set
        removed = original_set - modified_set

        # Detect migrations (package renames)
        # Check for known migrations from package_changes.py
        for removed_pkg in list(removed):
            # Check if this is a known migration
            migration = self._find_migration(
                removed_pkg, build_request.version, build_request
            )
            if migration and migration in added:
                self.changes.append(
                    PackageChange(
                        change_type="migration",
                        action="replace",
                        from_package=removed_pkg,
                        to_package=migration,
                        reason=f"Package renamed in {build_request.version}",
                        automatic=True,
                    )
                )
                removed.remove(removed_pkg)
                added.remove(migration)

        # Remaining removals
        for pkg in removed:
            self.changes.append(
                PackageChange(
                    change_type="removal",
                    action="remove",
                    package=pkg,
                    reason="Package no longer available or needed",
                    automatic=True,
                )
            )

        # Remaining additions
        for pkg in added:
            reason = self._get_addition_reason(pkg, build_request)
            self.changes.append(
                PackageChange(
                    change_type="addition",
                    action="add",
                    package=pkg,
                    reason=reason,
                    automatic=True,
                )
            )

    def _find_migration(
        self, package: str, version: str, build_request: BuildRequest
    ) -> Optional[str]:
        """Find if package was migrated to another name"""
        # Check for known migrations
        if version.startswith("24.10"):
            if package == "auc":
                return "owut"

        # Check for language pack renames
        from asu.package_changes import language_packs

        for lang_version, packages in language_packs.items():
            if version >= lang_version:
                for old, new in packages.items():
                    if package.startswith(old):
                        lang = package.replace(old, "")
                        return f"{new}{lang}"

        return None

    def _get_addition_reason(self, package: str, build_request: BuildRequest) -> str:
        """Determine why package was added"""
        if package.startswith("kmod-"):
            # Check if it's a hardware-specific module
            if build_request.target:
                return f"Required kernel module for {build_request.target}"
            return "Required kernel module"

        if package.startswith("luci-i18n-"):
            return "Language pack"

        if package.startswith("xrx200-"):
            return "Required PHY firmware"

        return "Required for this version/target/profile"
