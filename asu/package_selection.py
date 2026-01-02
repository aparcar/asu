"""Package selection logic for ASU.

This module provides functions to determine package selections for OpenWrt builds,
including default packages, profile-specific packages, and handling diff_packages logic.
"""

import logging
import re
from typing import Optional

from asu.build_request import BuildRequest
from asu.package_changes import apply_package_changes
from asu.util import diff_packages

log = logging.getLogger("rq.worker")


def get_default_packages(imagebuilder_output: str) -> set[str]:
    """Extract default packages from ImageBuilder output.

    Args:
        imagebuilder_output: The stdout from 'make info' command

    Returns:
        Set of default package names
    """
    match = re.search(r"Default Packages: (.*)\n", imagebuilder_output)
    if not match:
        return set()
    return set(match.group(1).split())


def get_profile_packages(imagebuilder_output: str, profile: str) -> set[str]:
    """Extract profile-specific packages from ImageBuilder output.

    Args:
        imagebuilder_output: The stdout from 'make info' command
        profile: The profile name to extract packages for

    Returns:
        Set of profile-specific package names
    """
    match = re.search(
        r"{}:\n    .+\n    Packages: (.*?)\n".format(profile),
        imagebuilder_output,
        re.MULTILINE,
    )
    if not match:
        return set()
    return set(match.group(1).split())


def calculate_package_selection(
    build_request: BuildRequest, default_packages: set[str], profile_packages: set[str]
) -> list[str]:
    """Calculate final package selection based on request parameters.

    This function handles:
    - Package changes/replacements via apply_package_changes
    - diff_packages logic (absolute vs additional package lists)
    - Preserves user-specified package ordering

    Args:
        build_request: The build request containing package specifications
        default_packages: Set of default packages from ImageBuilder
        profile_packages: Set of profile-specific packages from ImageBuilder

    Returns:
        List of packages formatted for ImageBuilder build command
    """
    # Apply any version-specific or profile-specific package changes
    apply_package_changes(build_request)

    build_cmd_packages = build_request.packages

    if build_request.diff_packages:
        # When diff_packages is True, treat requested packages as absolute
        # and remove all default/profile packages not in the request
        build_cmd_packages = diff_packages(
            build_request.packages, default_packages | profile_packages
        )
        log.debug(f"Diffed packages: {build_cmd_packages}")

    return build_cmd_packages


def validate_package_manifest(
    manifest: dict[str, str], requested_versions: dict[str, str]
) -> Optional[str]:
    """Validate that manifest matches requested package versions.

    Args:
        manifest: Dictionary mapping package names to versions from manifest
        requested_versions: Dictionary of requested package names and versions

    Returns:
        Error message if validation fails, None if valid
    """
    for package, version in requested_versions.items():
        if package not in manifest:
            return f"Impossible package selection: {package} not in manifest"
        if version != manifest[package]:
            return (
                f"Impossible package selection: {package} version not as requested: "
                f"{version} vs. {manifest[package]}"
            )
    return None
