"""
PrepareRequest model for the prepare service.

This is a minimal model that only includes fields needed for package
resolution and migration. Fields like defaults, rootfs_size_mb, 
repositories, etc. are NOT needed for the prepare step - those are
only relevant for the actual build step.

The prepare service only needs to know:
- What version/target/profile you're building for
- What packages you want
- What version you're upgrading from (for migrations)
"""

from typing import Annotated

from pydantic import BaseModel, Field

STRING_PATTERN = r"^[\w.,-]*$"
TARGET_PATTERN = r"^[\w]*/[\w]*$"


class PrepareRequest(BaseModel):
    """
    Minimal request for the prepare endpoint.
    
    This only includes fields needed to resolve packages and apply migrations.
    All build-specific fields (defaults, rootfs_size_mb, repositories, etc.)
    are handled by the build service, not the prepare service.
    """

    version: Annotated[
        str,
        Field(
            examples=["23.05.2", "24.10.0", "SNAPSHOT"],
            description="""
                The OpenWrt version to build for. This determines which
                package migrations and changes should be applied.
            """.strip(),
            pattern=STRING_PATTERN,
        ),
    ]

    target: Annotated[
        str,
        Field(
            examples=["ath79/generic", "x86/64", "mediatek/mt7622"],
            description="""
                The target platform. This determines which hardware-specific
                packages need to be added (e.g., kernel modules, firmware).
            """.strip(),
            pattern=TARGET_PATTERN,
        ),
    ]

    profile: Annotated[
        str,
        Field(
            examples=["tplink_tl-wdr4300-v1", "generic", "linksys_e4200-v2"],
            description="""
                The device profile. Some profiles require specific packages
                (e.g., switch drivers, PHY firmware).
            """.strip(),
            pattern=STRING_PATTERN,
        ),
    ]

    packages: Annotated[
        list[Annotated[str, Field(pattern=STRING_PATTERN)]],
        Field(
            examples=[["luci", "vim", "tmux"], ["auc", "luci-i18n-opkg-en"]],
            description="""
                List of packages to include in the build. The prepare service
                will apply migrations (e.g., auc → owut) and add required
                hardware-specific packages.
            """.strip(),
        ),
    ] = []

    from_version: Annotated[
        str | None,
        Field(
            examples=["23.05.0", "24.10.0"],
            description="""
                Optional: The version the device is currently running.
                This can be used for future migration logic that depends
                on the upgrade path, but is not currently used.
            """.strip(),
            pattern=STRING_PATTERN,
        ),
    ] = None

    distro: Annotated[
        str,
        Field(
            description="""
                Distribution name. Currently only 'openwrt' is supported.
                Included for consistency with build API.
            """.strip(),
            pattern=STRING_PATTERN,
        ),
    ] = "openwrt"
