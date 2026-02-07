import os
import tempfile
import time

import yaml

from asu.branches import _load_branches, get_branches


def _make_openwrt_yaml(branches):
    """Wrap a branches dict in a full openwrt.yaml structure."""
    return {
        "branches": branches,
        "revision_changes": [],
        "version_changes": [],
        "language_packs": [],
    }


def test_load_branches_from_yaml():
    branches = get_branches()
    assert "SNAPSHOT" in branches
    assert branches["SNAPSHOT"]["snapshot"] is True
    assert branches["SNAPSHOT"]["path"] == "snapshots"

    assert "24.10" in branches
    assert branches["24.10"]["branch_off_rev"] == 27990
    assert branches["24.10"]["path"] == "releases/{version}"
    assert branches["24.10"]["enabled"] is True


def test_load_branches_defaults():
    """Non-SNAPSHOT branches get sensible defaults."""
    branches = get_branches()
    for name, branch in branches.items():
        if name == "SNAPSHOT":
            continue
        assert branch["path"] == "releases/{version}"
        assert branch["enabled"] is True
        assert branch["snapshot"] is False


def test_branches_auto_reload():
    """Verify that modifying the YAML file causes a reload."""
    raw = _make_openwrt_yaml({"test-branch": {"branch_off_rev": 99999}})

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(raw, f)
        tmp_path = f.name

    try:
        data = _load_branches(tmp_path)
        assert "test-branch" in data
        assert data["test-branch"]["branch_off_rev"] == 99999

        # Ensure mtime changes
        time.sleep(0.05)

        raw["branches"]["new-branch"] = {"branch_off_rev": 11111}
        with open(tmp_path, "w") as f:
            yaml.dump(raw, f)

        data = _load_branches(tmp_path)
        assert "new-branch" in data
        assert data["new-branch"]["branch_off_rev"] == 11111
    finally:
        os.unlink(tmp_path)


def test_branches_numeric_keys_coerced_to_str():
    """YAML numeric keys (e.g. unquoted 21.02) are coerced to strings."""
    # Simulate unquoted numeric key — yaml.dump will produce a float key
    raw = _make_openwrt_yaml({21.02: {"branch_off_rev": 15812}})

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(raw, f)
        tmp_path = f.name

    try:
        data = _load_branches(tmp_path)
        assert "21.02" in data
    finally:
        os.unlink(tmp_path)
