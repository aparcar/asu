import logging

from asu.build_request import BuildRequest

log = logging.getLogger("rq.worker")


# Language pack replacements are done generically on a per-version basis.
# Note that the version comparison below applies to all versions the same
# or newer, so for example "24.10" applies to snapshots, too.
language_packs = {
    "24.10": {
        "luci-i18n-opkg-": "luci-i18n-package-manager-",
    },
}


def apply_package_changes(build_request: BuildRequest):
    """
    Apply package changes to the request

    Args:
        req (dict): The image request
        log (logging.Logger): The logger to use
    """

    def _add_if_missing(package):
        if package not in build_request.packages:
            build_request.packages.append(package)
            log.debug(f"Added {package} to packages")

    # 23.05 specific changes
    if build_request.version.startswith("23.05"):
        # mediatek/mt7622 specific changes
        if build_request.target == "mediatek/mt7622":
            _add_if_missing("kmod-mt7622-firmware")

        # ath79/generic specific changes
        elif build_request.target == "ath79/generic":
            if build_request.profile in {
                "buffalo_wzr-hp-g300nh-s",
                "dlink_dir-825-b1",
                "netgear_wndr3700",
                "netgear_wndr3700-v2",
                "netgear_wndr3800",
                "netgear_wndr3800ch",
                "netgear_wndrmac-v1",
                "netgear_wndrmac-v2",
                "trendnet_tew-673gru",
            }:
                _add_if_missing("kmod-switch-rtl8366s")

            elif build_request.profile == "buffalo_wzr-hp-g300nh-rb":
                _add_if_missing("kmod-switch-rtl8366rb")

    if build_request.version.startswith("24.10"):
        # `auc` no longer exists here
        if "auc" in build_request.packages:
            build_request.packages.remove("auc")
            _add_if_missing("owut")

        if build_request.profile in {"tplink_archer-c6-v2"}:
            _add_if_missing("ipq-wifi-tplink_archer-c6-v2")

        if build_request.target in {
            "mediatek/filogic",
            "mediatek/mt7622",
            "mediatek/mt7623",
        }:
            _add_if_missing("fitblk")

    # 25.12 specific changes
    if build_request.version.startswith("25.12"):
        # Changes for https://github.com/openwrt/openwrt/commit/8a7239009c5f4b28b696042b70ed1f8f89902915
        if build_request.target == "kirkwood/generic":
            if build_request.profile in {
                "checkpoint_l-50",
                "endian_4i-edge-200",
                "linksys_e4200-v2",
                "linksys_ea3500",
                "linksys_ea4500",
            }:
                _add_if_missing("kmod-dsa-mv88e6xxx")
        # Changes for https://github.com/openwrt/openwrt/commit/eaa82118eadfd495f8512d55c01c1935b8b42c51
        elif build_request.target == "mvebu/cortexa9":
            if build_request.profile in {
                "cznic_turris-omnia",
                "fortinet_fg-30e",
                "fortinet_fwf-30e",
                "fortinet_fg-50e",
                "fortinet_fg-51e",
                "fortinet_fg-52e",
                "fortinet_fwf-50e-2r",
                "fortinet_fwf-51e",
                "iij_sa-w2",
                "linksys_wrt1200ac",
                "linksys_wrt1900acs",
                "linksys_wrt1900ac-v1",
                "linksys_wrt1900ac-v2",
                "linksys_wrt3200acm",
                "linksys_wrt32x",
                "marvell_a370-rd",
            }:
                _add_if_missing("kmod-dsa-mv88e6xxx")
        # Changes for https://github.com/openwrt/openwrt/commit/eaa82118eadfd495f8512d55c01c1935b8b42c51
        elif build_request.target == "mvebu/cortexa53":
            if build_request.profile in {
                "glinet_gl-mv1000",
                "globalscale_espressobin",
                "globalscale_espressobin-emmc",
                "globalscale_espressobin-ultra",
                "globalscale_espressobin-v7",
                "globalscale_espressobin-v7-emmc",
                "methode_udpu",
            }:
                _add_if_missing("kmod-dsa-mv88e6xxx")
        # Changes for https://github.com/openwrt/openwrt/commit/eaa82118eadfd495f8512d55c01c1935b8b42c51
        elif build_request.target == "mvebu/cortexa72":
            if build_request.profile in {
                "checkpoint_v-80",
                "checkpoint_v-81",
                "globalscale_mochabin",
                "mikrotik_rb5009",
                "solidrun_clearfog-pro",
            }:
                _add_if_missing("kmod-dsa-mv88e6xxx")
        # Changes for https://github.com/openwrt/openwrt/commit/a18d95f35bd54ade908e8ec3158435859402552d
        elif build_request.target == "lantiq/xrx200":
            if build_request.profile in {
                "arcadyan_arv7519rw22",
                "arcadyan_vgv7510kw22-brn",
                "arcadyan_vgv7510kw22-nor",
                "avm_fritz7412",
                "avm_fritz7430",
                "buffalo_wbmr-300hpd",
            }:
                _add_if_missing("xrx200-rev1.1-phy22f-firmware")
                _add_if_missing("xrx200-rev1.2-phy22f-firmware")
            elif build_request.profile in {
                "tplink_vr200",
                "tplink_vr200v",
                "arcadyan_vgv7519-brn",
                "arcadyan_vgv7519-nor",
                "arcadyan_vrv9510kwac23",
                "avm_fritz3370-rev2-hynix",
                "avm_fritz3370-rev2-micron",
                "avm_fritz3390",
                "avm_fritz3490",
                "avm_fritz3490-micron",
                "avm_fritz5490",
                "avm_fritz5490-micron",
                "avm_fritz7360sl",
                "avm_fritz7360-v2",
                "avm_fritz7362sl",
                "avm_fritz7490",
                "avm_fritz7490-micron",
                "bt_homehub-v5a",
                "lantiq_easy80920-nand",
                "lantiq_easy80920-nor",
                "zyxel_p-2812hnu-f1",
                "zyxel_p-2812hnu-f3",
            }:
                _add_if_missing("xrx200-rev1.1-phy11g-firmware")
                _add_if_missing("xrx200-rev1.2-phy11g-firmware")
        # Changes for https://github.com/openwrt/openwrt/commit/a18d95f35bd54ade908e8ec3158435859402552d
        elif build_request.target == "lantiq/xrx200_legacy":
            if build_request.profile in {
                "alphanetworks_asl56026",
                "netgear_dm200",
            }:
                _add_if_missing("xrx200-rev1.1-phy22f-firmware")
                _add_if_missing("xrx200-rev1.2-phy22f-firmware")
            elif build_request.profile in {
                "tplink_tdw8970",
                "tplink_tdw8980",
                "arcadyan_vg3503j",
            }:
                _add_if_missing("xrx200-rev1.1-phy11g-firmware")
                _add_if_missing("xrx200-rev1.2-phy11g-firmware")
        # Changes for https://github.com/openwrt/openwrt/commit/3b7a92754e81432024b232c7cd7fe32593891ee0
        elif build_request.target == "bcm53xx/generic":
            if build_request.profile in {
                "meraki_mr32",
            }:
                _add_if_missing("kmod-hci-uart")
        elif build_request.target == "ipq40xx/generic":
            if build_request.profile in {
                "linksys_whw03",
                "linksys_whw03v2",
            }:
                _add_if_missing("kmod-hci-uart")
        elif build_request.target == "qualcommax/ipq807x":
            if build_request.profile in {
                "linksys_mx4200v1",
                "linksys_mx8500",
                "zyxel_nbg7815",
            }:
                _add_if_missing("kmod-hci-uart")

    # TODO: if we ever fully implement 'packages_versions', this needs rework
    for version, packages in language_packs.items():
        if build_request.version >= version:  # Includes snapshots
            for i, package in enumerate(build_request.packages):
                for old, new in packages.items():
                    if package.startswith(old):
                        lang = package.replace(old, "")
                        build_request.packages[i] = f"{new}{lang}"
