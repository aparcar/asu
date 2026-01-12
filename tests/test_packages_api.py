"""Test the new package selection API endpoints"""


def test_packages_defaults_endpoint(client):
    """Test the GET /api/v1/packages/defaults endpoint"""
    response = client.get("/api/v1/packages/defaults/1.2.3/testtarget/testsubtarget")
    assert response.status_code == 200
    data = response.json()
    assert "packages" in data
    assert isinstance(data["packages"], list)


def test_packages_profile_endpoint(client):
    """Test the GET /api/v1/packages/profile endpoint"""
    response = client.get(
        "/api/v1/packages/profile/1.2.3/testtarget/testsubtarget/testprofile"
    )
    assert response.status_code == 200
    data = response.json()
    assert "packages" in data
    assert isinstance(data["packages"], list)


def test_packages_select_endpoint(client):
    """Test the POST /api/v1/packages/select endpoint"""
    response = client.post(
        "/api/v1/packages/select",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["vim", "tmux"],
            diff_packages=False,
        ),
    )
    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "default_packages" in data
    assert "profile_packages" in data
    assert "final_packages" in data
    assert "packages_to_add" in data
    assert "packages_to_remove" in data

    # Verify types
    assert isinstance(data["default_packages"], list)
    assert isinstance(data["profile_packages"], list)
    assert isinstance(data["final_packages"], list)

    # With diff_packages=False, final_packages should just be the requested packages
    assert data["final_packages"] == ["vim", "tmux"]


def test_packages_select_endpoint_with_diff(client):
    """Test the POST /api/v1/packages/select endpoint with diff_packages=True"""
    response = client.post(
        "/api/v1/packages/select",
        json=dict(
            version="1.2.3",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["vim", "tmux"],
            diff_packages=True,
        ),
    )
    assert response.status_code == 200
    data = response.json()

    # With diff_packages=True, should have both removals and additions
    final = data["final_packages"]

    # Should have some packages to remove (starting with -)
    assert any(p.startswith("-") for p in final)

    # Should include requested packages
    assert "vim" in final
    assert "tmux" in final


def test_packages_select_endpoint_invalid_version(client):
    """Test package select with invalid version"""
    response = client.post(
        "/api/v1/packages/select",
        json=dict(
            version="99.99.99",
            target="testtarget/testsubtarget",
            profile="testprofile",
            packages=["vim"],
        ),
    )
    # Should fail validation
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "status" in data


def test_packages_select_endpoint_invalid_target(client):
    """Test package select with invalid target"""
    response = client.post(
        "/api/v1/packages/select",
        json=dict(
            version="1.2.3",
            target="invalid/target",
            profile="testprofile",
            packages=["vim"],
        ),
    )
    # Should fail validation
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "status" in data
