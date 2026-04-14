"""Security regression tests for issues found in the 2026-02-06 audit."""

import pytest

from asu.build_request import BuildRequest
from asu.config import settings


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


def test_repositories_mode_accepts_append_and_replace():
    append_request = BuildRequest(
        version="1.2.3",
        target="testtarget/testsubtarget",
        profile="testprofile",
        repositories_mode="append",
    )
    replace_request = BuildRequest(
        version="1.2.3",
        target="testtarget/testsubtarget",
        profile="testprofile",
        repositories_mode="replace",
    )
    assert append_request.repositories_mode == "append"
    assert replace_request.repositories_mode == "replace"


def test_repositories_mode_rejects_invalid_value():
    with pytest.raises(Exception):
        BuildRequest(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            repositories_mode="invalid",
        )


def test_api_repositories_mode_rejects_invalid_value(client):
    response = client.post(
        "/api/v1/build",
        json={
            "version": "1.2.3",
            "target": "testtarget/testsubtarget",
            "profile": "testprofile",
            "repositories_mode": "invalid",
        },
    )
    assert response.status_code == 422


def test_api_repo_not_in_allow_list(client):
    """Repositories not in the allow list must be rejected at the API level."""
    settings.repository_allow_list = ["https://allowed.example.com/"]
    response = client.post(
        "/api/v1/build",
        json={
            "version": "1.2.3",
            "target": "testtarget/testsubtarget",
            "profile": "testprofile",
            "repositories": {
                "evil": "https://evil.example.com/packages",
            },
        },
    )
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]
