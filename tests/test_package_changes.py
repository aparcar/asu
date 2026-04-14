from asu.build_request import BuildRequest
from asu.package_changes import apply_package_changes


def test_apply_package_changes_adds_kmod_switch_rtl8366s():
    build_request = BuildRequest(
        **{
            "version": "23.05",
            "target": "ath79/generic",
            "profile": "buffalo_wzr-hp-g300nh-s",
            "packages": ["kmod-ath9k-htc"],
        }
    )
    apply_package_changes(build_request)

    assert "kmod-switch-rtl8366s" in build_request.packages


def test_apply_package_changes_does_not_add_duplicate_packages():
    build_request = BuildRequest(
        **{
            "version": "23.05",
            "target": "ath79/generic",
            "profile": "buffalo_wzr-hp-g300nh-s",
            "packages": ["kmod-ath9k-htc", "kmod-switch-rtl8366s"],
        }
    )
    apply_package_changes(build_request)

    assert build_request.packages == ["kmod-ath9k-htc", "kmod-switch-rtl8366s"]


def test_apply_package_changes_does_not_modify_input_dict():
    build_request = BuildRequest(
        **{
            "version": "23.05",
            "target": "ath79/generic",
            "profile": "buffalo_wzr-hp-g300nh-s",
            "packages": ["kmod-ath9k-htc"],
        }
    )
    original_req = build_request.model_copy()
    apply_package_changes(build_request)

    assert build_request == original_req


def test_apply_package_add_and_remove():
    build_request = BuildRequest(
        **{
            "version": "24.10",
            "target": "ath79/generic",
            "profile": "buffalo_wzr-hp-g300nh-s",
            "packages": ["auc"],
        }
    )
    apply_package_changes(build_request)

    assert "owut" in build_request.packages

    build_request.version = "SNAPSHOT"
    build_request.packages = [
        "a",
        "b",
        "kmod-nf-conntrack",
        "c",
        "kmod-nf-conntrack6",
        "d",
        "e",
    ]

    assert len(build_request.packages) == 7

    apply_package_changes(build_request)

    assert len(build_request.packages) == 6
    assert "kmod-nf-conntrack" in build_request.packages
    assert "kmod-nf-conntrack6" not in build_request.packages


def test_apply_package_changes_release():
    build_request = BuildRequest(
        **{
            "version": "21.02.0-rc1",
            "target": "ath79/generic",
            "profile": "buffalo_wzr-hp-g300nh-s",
            "packages": ["kmod-ath9k-htc"],
        }
    )
    apply_package_changes(build_request)

    original_build_request = build_request.model_copy()
    apply_package_changes(build_request)

    assert build_request == original_build_request


def test_apply_package_changes_mediatek():
    build_request = BuildRequest(
        **{
            "version": "23.05",
            "target": "mediatek/mt7622",
            "profile": "foobar",
            "packages": ["ubus"],
        }
    )
    apply_package_changes(build_request)

    assert "kmod-mt7622-firmware" in build_request.packages


def test_apply_package_changes_lang_packs():
    build_request = BuildRequest(
        **{
            "version": "23.05.5",
            "target": "mediatek/mt7622",
            "profile": "foobar",
            "packages": [
                "luci-i18n-english-en",  # Should be deleted
                "luci-i18n-opkg-ko",  # Should be replaced
                "luci-i18n-xinetd-lt",  # Should be untouched
                "luci-i18n-opkg-en",  # Should be deleted
                "luci-i18n-opkg-zh-cn",  # Should be replaced
            ],
        }
    )

    assert len(build_request.packages) == 5
    assert build_request.packages[0] == "luci-i18n-english-en"
    assert build_request.packages[1] == "luci-i18n-opkg-ko"
    assert build_request.packages[2] == "luci-i18n-xinetd-lt"
    assert build_request.packages[3] == "luci-i18n-opkg-en"
    assert build_request.packages[4] == "luci-i18n-opkg-zh-cn"

    apply_package_changes(build_request)

    assert len(build_request.packages) == 4
    assert build_request.packages[0] == "luci-i18n-opkg-ko"
    assert build_request.packages[1] == "luci-i18n-xinetd-lt"
    assert build_request.packages[2] == "luci-i18n-opkg-zh-cn"
    assert build_request.packages[3] == "kmod-mt7622-firmware"

    build_request.version = "24.10.0-rc5"
    apply_package_changes(build_request)

    assert len(build_request.packages) == 5
    assert build_request.packages[0] == "luci-i18n-package-manager-ko"
    assert build_request.packages[1] == "luci-i18n-xinetd-lt"
    assert build_request.packages[2] == "luci-i18n-package-manager-zh-cn"
    assert build_request.packages[3] == "kmod-mt7622-firmware"
    assert build_request.packages[4] == "fitblk"
