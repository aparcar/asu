from asu.repositories import merge_repositories


def test_merge_opkg_appends():
    base = "src/gz base https://example.com/base\noption check_signature\n"
    merged = merge_repositories(
        base,
        {"custom": "https://example.com/custom"},
        apk_mode=False,
    )
    assert "src/gz base https://example.com/base" in merged
    assert "src/gz custom https://example.com/custom" in merged
    assert "option check_signature" in merged
    assert "src imagebuilder file:packages" in merged


def test_merge_opkg_adds_required_lines():
    merged = merge_repositories(
        "",
        {"custom": "https://example.com/custom"},
        apk_mode=False,
    )
    assert "src imagebuilder file:packages" in merged
    assert "option check_signature" in merged


def test_merge_opkg_replace_mode():
    merged = merge_repositories(
        "",
        {"foo": "https://example.com/foo", "bar": "https://example.com/bar"},
        apk_mode=False,
    )
    assert "src/gz bar https://example.com/bar" in merged
    assert "src/gz foo https://example.com/foo" in merged
    assert "option check_signature" in merged


def test_merge_apk_appends():
    base = "https://example.com/a\nhttps://example.com/b\n"
    merged = merge_repositories(
        base,
        {"x": "https://example.com/c"},
        apk_mode=True,
    )
    assert "https://example.com/a" in merged
    assert "https://example.com/b" in merged
    assert "https://example.com/c" in merged


def test_merge_apk_replace_mode():
    merged = merge_repositories(
        "",
        {"x": "https://example.com/new"},
        apk_mode=True,
    )
    assert "https://example.com/new" in merged
