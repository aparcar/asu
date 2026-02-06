from typing import Annotated

from pydantic import BaseModel, Field

from asu.config import settings

STRING_PATTERN = r"^[\w.,-]*$"
TARGET_PATTERN = r"^[\w]*/[\w]*$"
PKG_VERSION_PATTERN = r"^[\w+.,~-]*$"
REPO_NAME_PATTERN = r"^[\w.-]+$"
REPO_URL_PATTERN = r"^https?://\S+$"


class BuildRequest(BaseModel):
    distro: Annotated[
        str,
        Field(
            description="""
                This parameter is currently optional since no other
                distributions are supported.
            """.strip(),
            pattern=STRING_PATTERN,
        ),
    ] = "openwrt"
    version: Annotated[
        str,
        Field(
            examples=["23.05.2"],
            description="""
                It is recommended to always upgrade to the latest version,
                however it is possible to request older images for testing.
            """.strip(),
            pattern=STRING_PATTERN,
        ),
    ]
    version_code: Annotated[
        str,
        Field(
            examples=["r26741-dcc4307205"],
            description="""
                It is possible to send the expected revision.  This allows to
                show the revision within clients before the request. If the
                resulting firmware is a different revision, the build results
                in an error.
            """.strip(),
            pattern=STRING_PATTERN,
        ),
    ] = ""
    target: Annotated[
        str,
        Field(
            examples=["ath79/generic"],
            description="""
            It is recommended to always upgrade to the latest version, however
            it is possible to request older images for testing.
            """.strip(),
            pattern=TARGET_PATTERN,
        ),
    ]
    profile: Annotated[
        str,
        Field(
            examples=["8dev_carambola2"],
            description="""
                The ImageBuilder `PROFILE`.  Can be found with `ubus call
                system board` as the `board_name` value.
                """.strip(),
            pattern=STRING_PATTERN,
        ),
    ]
    packages: Annotated[
        list[Annotated[str, Field(pattern=STRING_PATTERN)]],
        Field(
            examples=[["vim", "tmux"]],
            description="""
                List of packages, either *additional* or *absolute* depending
                of the `diff_packages` parameter.  This is augmented by the
                `packages_versions` field, which allow you to additionally
                specify the versions of the packages to be installed.
            """.strip(),
        ),
    ] = []
    packages_versions: Annotated[
        dict[
            Annotated[str, Field(pattern=STRING_PATTERN)],
            Annotated[str, Field(pattern=PKG_VERSION_PATTERN)],
        ],
        Field(
            examples=[{"vim": "1.2.3", "tmux": "2.3.4"}],
            description="""
                A dictionary of package names and versions.  This is an
                alternate form of `packages`, in which the expected package
                versions are specified for verification after the build has
                completed.
            """.strip(),
        ),
    ] = {}
    diff_packages: Annotated[
        bool,
        Field(
            description="""
                This parameter determines if requested packages are seen as
                *additional* or *absolute*. If set to `true` the packages are
                seen as *absolute* and all default packages outside the
                requested packages are removed. \n\n It is possible to brick
                devices when requesting an incomplete list with this parameter
                enabled since it may remove WiFi drivers or other essential
                packages.
            """.strip(),
        ),
    ] = False
    defaults: Annotated[
        str | None,
        Field(
            max_length=settings.max_defaults_length,
            examples=['echo "Hello world"\nwifi restart\n'],
            description=f"""
                Custom shell script embedded in firmware image to be run
                on first boot. This feature might be dropped in the future.
                Input file size is limited to {settings.max_defaults_length}
                bytes and cannot be exceeded.
            """.strip(),
        ),
    ] = None
    rootfs_size_mb: Annotated[
        int | None,
        Field(
            ge=1,
            le=settings.max_custom_rootfs_size_mb,
            examples=[256],
            description="""
                Ability to specify a custom `CONFIG_TARGET_ROOTFS_PARTSIZE`
                for the resulting image. Attaching this optional parameter
                will cause ImageBuilder to build a rootfs with that size
                in MB.
            """.strip(),
        ),
    ] = None
    repositories: Annotated[
        dict[
            Annotated[str, Field(pattern=REPO_NAME_PATTERN)],
            Annotated[str, Field(pattern=REPO_URL_PATTERN)],
        ],
        Field(
            description="""
                Additional repositories for user packages.
            """.strip()
        ),
    ] = {}
    repository_keys: Annotated[
        list[str],
        Field(
            description="""
                    Verfication keys for the additional repositories.
                """.strip(),
        ),
    ] = []
    client: Annotated[
        str | None,
        Field(
            examples=["luci/git-22.073.39928-701ea94"],
            description="""
                Client name and version that requests the image,
            """.strip(),
        ),
    ] = None
