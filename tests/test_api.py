import pytest
from fastapi.testclient import TestClient

from asu.config import settings


def test_api_build(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["zzz", "test1", "qqq", "test2", "aaa"],
        ),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["manifest"]["test1"] == "1.0"
    assert data["build_cmd"][3] == "PACKAGES=zzz test1 qqq test2 aaa"


def test_api_build_inputs(client):
    """Check both the required and optional default values for all of the
    request values defined in the BuildRequest model."""

    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
        ),
    )
    assert response.status_code == 200
    data = response.json()

    request = data["request"]

    # Required
    assert request["version"] == "1.2.3"
    assert request["target"] == "testtarget/testsubtarget"
    assert request["profile"] == "testprofile"

    # Optional
    assert request["distro"] == "openwrt"
    assert request["version_code"] == ""
    assert request["packages"] == []
    assert request["packages_versions"] == {}
    assert request["defaults"] is None
    assert request["client"] is None
    assert request["rootfs_size_mb"] is None
    assert request["diff_packages"] is False


def test_api_build_version_code(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            version_code="r12647-cb44ab4f5d",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["test1", "test2"],
        ),
    )
    assert response.status_code == 200


def test_api_build_rootfs_size(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["test1", "test2"],
            rootfs_size_mb=100,
        ),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["build_cmd"][6] == "ROOTFS_PARTSIZE=100"


def test_api_build_rootfs_size_too_small(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["test1", "test2"],
            rootfs_size_mb=0,
        ),
    )
    assert response.status_code == 422
    data = response.json()
    assert data["detail"][0]["msg"] == "Input should be greater than or equal to 1"


def test_api_build_rootfs_size_too_big(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["test1", "test2"],
            rootfs_size_mb=settings.max_custom_rootfs_size_mb + 1,
        ),
    )
    assert response.status_code == 422
    data = response.json()
    assert (
        data["detail"][0]["msg"]
        == f"Input should be less than or equal to {settings.max_custom_rootfs_size_mb}"
    )


def test_api_build_version_code_bad(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            version_code="some-bad-version-code",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["test1", "test2"],
        ),
    )
    assert response.status_code == 500
    data = response.json()
    assert (
        data["detail"]
        == "Error: Received incorrect version r12647-cb44ab4f5d (requested some-bad-version-code)"
    )


def test_build_missing_container():
    from asu.build import build
    from asu.build_request import BuildRequest

    build_request = BuildRequest(
        client="test/1.2.3",
        target="lantiq/xrx200",
        profile="bt_homehub-v5a",
        version="24.10.1",
    )

    class fake_job:
        meta = {}

        def save_meta(self):
            pass

    try:
        build(build_request, fake_job())
    except Exception as exc:
        chain = exc
        while hasattr(chain, "__context__") and chain.__context__:
            # We want the original exception, not anything that FakeRedis
            # generated during processing of it.
            chain = chain.__context__
            if isinstance(chain, RuntimeError):
                exc = chain
                break
        assert str(exc).startswith(
            "Image not found: ghcr.io/openwrt/imagebuilder:lantiq-xrx200-v24.10.1"
        )
    else:
        assert False, "No exception raised!"


base_packages_diff = (
    "PACKAGES=-base-files -busybox -dnsmasq -dropbear -firewall -fstools"
    " -ip6tables -iptables -kmod-ath9k -kmod-gpio-button-hotplug"
    " -kmod-ipt-offload -kmod-usb-chipidea2 -kmod-usb-storage -kmod-usb2"
    " -libc -libgcc -logd -mtd -netifd -odhcp6c -odhcpd-ipv6only -opkg"
    " -ppp -ppp-mod-pppoe -swconfig -uboot-envtools -uci -uclient-fetch"
    " -urandom-seed -urngd -wpad-basic"
)


def test_api_build_diff_packages(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["test1", "zzz", "test2", "aaa"],  # Order must be maintained.
            diff_packages=True,
        ),
    )

    assert response.status_code == 200

    data = response.json()
    assert data["build_cmd"][3] == base_packages_diff + " test1 zzz test2 aaa"


def test_api_build_request_hash(client):
    """Verify that request hash is unchanged by different package ordering."""

    packages1 = ["test1", "zzz", "test2", "aaa"]
    packages2 = sorted(packages1)
    assert packages1 != packages2

    json = dict(
        version="1.2.3",
        target="testtarget/testsubtarget",
        profile="testprofile",
    )

    case12hash = "8d8e0aa2fd95bb75dba4aff4279dd6f976a40ad17300927d54b8a9a9b0576306"
    case34hash = "6b1645013216da39ee09deae75b87b0636f3c50648b037750b0a80448ce5c7ca"

    # Case 1 - diff_packages=True, first package ordering
    json["diff_packages"] = True
    json["packages"] = packages1
    response = client.post("/api/v1/build", json=json)

    assert response.status_code == 200
    data = response.json()
    assert data["build_cmd"][3] == base_packages_diff + " " + " ".join(packages1)
    assert data["request_hash"] == case12hash

    # Case 2 - diff_packages=True, second package ordering
    json["diff_packages"] = True
    json["packages"] = packages2
    response = client.post("/api/v1/build", json=json)

    assert response.status_code == 200
    data = response.json()
    assert data["request_hash"] == case12hash
    # This fails, because the returned build command comes from the one hashed
    # by the previous build...
    #   assert data["build_cmd"][3] == base_packages_diff + " " + " ".join(packages2)

    # Case 3 - diff_packages=False, first package ordering
    json["diff_packages"] = False
    json["packages"] = packages1
    response = client.post("/api/v1/build", json=json)

    assert response.status_code == 200
    data = response.json()
    assert data["build_cmd"][3] == "PACKAGES=" + " ".join(packages1)
    assert data["request_hash"] == case34hash

    # Case 4 - diff_packages=False, second package ordering
    json["diff_packages"] = False
    json["packages"] = packages2
    response = client.post("/api/v1/build", json=json)

    assert response.status_code == 200
    data = response.json()
    assert data["request_hash"] == case34hash
    # Same failure as case 2.
    #   assert data["build_cmd"][3] == "PACKAGES=" + " ".join(packages2)


def test_api_latest_default(client):
    response = client.get("/api/v1/latest", follow_redirects=False)
    assert response.status_code == 301


def test_api_overview(client):
    response = client.get("/api/v1/overview", follow_redirects=False)
    assert response.status_code == 301


def test_api_build_mapping(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["test1", "test2"],
        ),
    )
    assert response.status_code == 200


def test_api_build_mapping_abi(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["test1-1", "test2"],
        ),
    )
    assert response.status_code == 200


def test_api_build_bad_target(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtargetbad",
            profile="testvendor,testprofile",
            packages=["test1", "test2"],
        ),
    )
    assert response.status_code == 400
    data = response.json()
    assert (
        data.get("detail")
        == "Unsupported target: testtarget/testsubtargetbad. The requested "
        "target was either dropped, is still being built or is not supported "
        "by the selected version. Please check the forums or try again later."
    )


def test_api_build_head_get(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["test1", "test2"],
        ),
    )
    data = response.json()
    request_hash = data["request_hash"]

    # verify HEAD response and that it has no payload
    response = client.head(f"/api/v1/build/{request_hash}")
    assert response.status_code == 200

    headers = response.headers
    assert headers["x-imagebuilder-status"] == "done"
    assert headers["x-queue-position"] == "0"

    assert response.num_bytes_downloaded == 0
    data = response.text
    assert data == ""

    # verify GET response and its JSON payload
    response = client.get(f"/api/v1/build/{request_hash}")
    assert response.status_code == 200

    headers = response.headers
    assert headers["x-imagebuilder-status"] == "done"
    assert headers["x-queue-position"] == "0"

    assert response.num_bytes_downloaded > 0
    data = response.json()
    assert data["request_hash"] == request_hash
    assert data["imagebuilder_status"] == "done"
    request = data["request"]
    assert request["version"] == "1.2.3"
    assert request["target"] == "testtarget/testsubtarget"
    assert request["profile"] == "testprofile"


def test_api_build_packages_versions(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages_versions={"test1": "1.0", "test2": "2.0"},
        ),
    )
    data = response.json()
    request_hash = data["request_hash"]
    response = client.get(f"/api/v1/build/{request_hash}")
    assert response.status_code == 200
    data = response.json()
    assert data["request_hash"] == request_hash


def test_api_build_packages_versions_bad(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages_versions={"test1": "0.0", "test2": "2.0"},
        ),
    )
    data = response.json()
    request_hash = data["request_hash"]
    response = client.get(f"/api/v1/build/{request_hash}")
    assert response.status_code == 500
    assert (
        data["detail"]
        == "Error: Impossible package selection: test1 version not as requested: 0.0 vs. 1.0"
    )


def test_api_build_packages_duplicate(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["test1", "test2"],
            packages_versions={"test1": "1.0", "test2": "2.0"},
        ),
    )
    assert response.status_code == 200


def test_api_build_get_not_found(client):
    response = client.get("/api/v1/build/testtesttest")
    assert response.status_code == 404


def test_api_build_get_no_post(client):
    response = client.post("/api/v1/build/0222f0cd9290")
    assert response.status_code == 405


def test_api_build_empty_packages_list(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=[],
        ),
    )
    assert response.status_code == 200


@pytest.mark.slow
def test_api_build_conflicting_packages(client):
    """Use real build to get proper context for conflicts."""
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="23.05.5",
            target="ath79/generic",
            profile="8dev_carambola2",
            packages=["dnsmasq", "dnsmasq-full"],
        ),
    )

    assert response.status_code == 500
    data = response.json()
    assert data["detail"] == "Error: Impossible package selection"


def test_api_build_without_packages_list(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
        ),
    )
    assert response.status_code == 200


def test_api_build_bad_packages_str(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages="testpackage",
        ),
    )
    assert response.status_code == 422
    data = response.json()
    assert data["detail"] == [
        {
            "input": "testpackage",
            "loc": ["body", "packages"],
            "msg": "Input should be a valid list",
            "type": "list_type",
        }
    ]


def test_api_build_empty_request(client):
    response = client.post("/api/v1/build")
    assert response.status_code == 422
    data = response.json()
    assert data["detail"] == [
        {"input": None, "loc": ["body"], "msg": "Field required", "type": "missing"}
    ]


@pytest.mark.slow
def test_api_build_real_x86(app):
    client = TestClient(app)
    response = client.post(
        "/api/v1/build",
        json=dict(
            target="x86/64",
            version="23.05.5",
            packages=["tmux", "vim"],
            profile="some_random_cpu_which_doesnt_exists_as_profile",
        ),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "generic"

    response = client.post(
        "/api/v1/build",
        json=dict(
            target="x86/64",
            version="23.05.5",
            packages=["tmux", "vim"],
            profile="some_random_cpu_which_doesnt_exists_as_profile",
            filesystem="ext4",
        ),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "generic"


@pytest.mark.slow
def test_api_build_real_ath79(app):
    client = TestClient(app)
    response = client.post(
        "/api/v1/build",
        json=dict(
            target="ath79/generic",
            version="23.05.5",
            packages=["tmux", "vim"],
            profile="8dev,carambola2",  # Test unsanitized profile.
        ),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "8dev_carambola2"

    response = client.post(
        "/api/v1/build",
        json=dict(
            target="ath79/generic",
            version="23.05.5",
            packages=["tmux", "vim"],
            profile="8dev_carambola2",
            filesystem="squashfs",
        ),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "8dev_carambola2"


def test_api_build_needed(client):
    response = client.post(
        "/api/v1/build",
        json=dict(profile="testprofile", target="testtarget/testsubtarget"),
    )
    assert response.status_code == 422
    data = response.json()
    assert data["detail"] == [
        {
            "input": {"profile": "testprofile", "target": "testtarget/testsubtarget"},
            "loc": ["body", "version"],
            "msg": "Field required",
            "type": "missing",
        }
    ]
    response = client.post(
        "/api/v1/build",
        json=dict(version="1.2.3", target="testtarget/testsubtarget"),
    )
    assert response.status_code == 422
    data = response.json()
    assert data["detail"] == [
        {
            "type": "missing",
            "loc": ["body", "profile"],
            "msg": "Field required",
            "input": {"version": "1.2.3", "target": "testtarget/testsubtarget"},
        }
    ]

    response = client.post(
        "/api/v1/build", json=dict(version="1.2.3", profile="testprofile")
    )
    assert response.status_code == 422
    data = response.json()
    assert data["detail"] == [
        {
            "type": "missing",
            "loc": ["body", "target"],
            "msg": "Field required",
            "input": {"version": "1.2.3", "profile": "testprofile"},
        }
    ]


def test_api_build_bad_distro(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            distro="Foobar",
            target="testtarget/testsubtarget",
            version="1.2.3",
            profile="testprofile",
            packages=["test1", "test2"],
        ),
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "Unsupported distro: Foobar"


def test_api_build_bad_branch(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="10.10.10",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["test1", "test2"],
        ),
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "Unsupported branch: 10.10.10"


def test_api_build_bad_version(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="19.07.2",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["test1", "test2"],
        ),
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "Unsupported version: 19.07.2"


def test_api_build_bad_profile(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="Foobar",
            packages=["test1", "test2"],
        ),
    )
    assert response.status_code == 400

    data = response.json()
    assert (
        data["detail"] == "Unsupported profile: Foobar. The requested "
        "profile was either dropped or never existed. Please check the forums "
        "for more information."
    )


def test_api_build_defaults_empty(client):
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            defaults="",
        ),
    )
    assert response.status_code == 200


def test_api_build_defaults_filled_not_allowed(client):
    settings.allow_defaults = False
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            defaults="echo",
        ),
    )

    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "Handling `defaults` not enabled on server"


def test_api_build_defaults_filled_allowed(app):
    settings.allow_defaults = True
    client = TestClient(app)
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            defaults="echo",
        ),
    )

    assert response.status_code == 200
    data = response.json()
    assert (
        data["request_hash"]
        == "9c8d0cd7d9ec208a233b954edb20c3c20b5c11103bb7f5f1ebface565f8c6720"
    )


def test_api_build_defaults_filled_too_big(app):
    settings.allow_defaults = True
    client = TestClient(app)
    response = client.post(
        "/api/v1/build",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            defaults="#" * (settings.max_defaults_length + 1),
        ),
    )

    assert response.status_code == 422
    data = response.json()
    assert (
        data["detail"][0]["msg"]
        == f"String should have at most {settings.max_defaults_length} characters"
    )


def test_api_revision(client):
    response = client.get(
        "/api/v1/revision/23.05.5/ath79/generic", follow_redirects=False
    )
    assert response.status_code == 200
    data = response.json()
    assert data["revision"] == "r24106-10cc5fcd00"


def test_api_stats(client):
    response = client.get("/api/v1/stats", follow_redirects=False)
    assert response.status_code == 200
    data = response.json()
    assert data["queue_length"] == 0


def test_api_build_prepare(client):
    """Test the prepare endpoint"""
    response = client.post(
        "/api/v1/build/prepare",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["test1", "test2"],
        ),
    )
    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert data["status"] == "prepared"
    assert "original_packages" in data
    assert "resolved_packages" in data
    assert "changes" in data
    assert "prepared_request" in data
    assert "request_hash" in data
    assert "cache_available" in data

    # Check original packages
    assert data["original_packages"] == ["test1", "test2"]

    # Check prepared request structure
    prepared = data["prepared_request"]
    assert prepared["version"] == "1.2.3"
    assert prepared["target"] == "testtarget/testsubtarget"
    assert prepared["profile"] == "testprofile"
    assert prepared["diff_packages"] is False  # Should be False after preparation


def test_api_build_prepare_with_auc_migration(client):
    """Test prepare endpoint with auc → owut migration"""
    response = client.post(
        "/api/v1/build/prepare",
        json=dict(
            version="24.10.0",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["luci", "auc"],
        ),
    )
    assert response.status_code == 200
    data = response.json()

    # Check that auc was replaced with owut
    assert "owut" in data["resolved_packages"]
    assert "auc" not in data["resolved_packages"]

    # Check changes
    assert len(data["changes"]) >= 1
    migration = next(
        (c for c in data["changes"] if c.get("from_package") == "auc"), None
    )
    assert migration is not None
    assert migration["type"] == "migration"
    assert migration["to_package"] == "owut"


def test_api_build_prepare_validation_error(client):
    """Test prepare endpoint with invalid version"""
    response = client.post(
        "/api/v1/build/prepare",
        json=dict(
            version="99.99.99",  # Invalid version
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["test1"],
        ),
    )
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data


def test_api_build_from_prepared_request(client):
    """Test building from a prepared request"""
    # First, prepare the request
    prep_response = client.post(
        "/api/v1/build/prepare",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["test1", "test2"],
        ),
    )
    assert prep_response.status_code == 200
    prep_data = prep_response.json()

    # Then build using the prepared request
    build_response = client.post(
        "/api/v1/build?skip_package_resolution=true",
        json=prep_data["prepared_request"],
    )
    assert build_response.status_code == 200
    build_data = build_response.json()

    # Verify the build used the prepared packages
    assert build_data["request"]["packages"] == prep_data["resolved_packages"]


def test_api_build_with_skip_package_resolution_flag(client):
    """Test that skip_package_resolution flag works correctly"""
    # Build with auc but skip package resolution
    response = client.post(
        "/api/v1/build?skip_package_resolution=true",
        json=dict(
            version="24.10.0",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["owut"],  # Already migrated
            diff_packages=False,
        ),
    )
    assert response.status_code == 200
    data = response.json()

    # Should keep owut, not try to migrate
    assert "owut" in data["request"]["packages"]


def test_api_build_prepare_with_from_version(client):
    """Test prepare endpoint with from_version parameter"""
    response = client.post(
        "/api/v1/build/prepare",
        json=dict(
            version="24.10.0",
            from_version="23.05.0",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["luci"],
        ),
    )
    assert response.status_code == 200
    data = response.json()

    # Check that from_version is preserved in prepared request
    assert data["prepared_request"]["from_version"] == "23.05.0"
