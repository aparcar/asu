import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from asu.config import settings


def pytest_addoption(parser):
    parser.addoption(
        "--runslow", action="store_true", default=False, help="run slow tests"
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow to run")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runslow"):
        # --runslow given in cli: do not skip slow tests
        return
    skip_slow = pytest.mark.skip(reason="need --runslow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


@pytest.fixture
def test_path():
    test_path = tempfile.mkdtemp(dir=Path.cwd() / "tests")
    yield test_path
    shutil.rmtree(test_path)


@pytest.fixture
def app(test_path, monkeypatch, upstream):
    from asu.database import init_database, close_database
    from asu.job_queue import init_queue, shutdown_queue
    
    settings.public_path = Path(test_path) / "public"
    settings.database_path = Path(test_path) / "test.db"
    settings.async_queue = False
    settings.upstream_url = "http://localhost:8123"
    settings.server_stats = "stats"
    settings.worker_threads = 2
    
    for branch in "1.2", "19.07", "21.02":
        if branch not in settings.branches:
            settings.branches[branch] = {
                "path": "releases/{version}",
                "enabled": True,
            }

    # Initialize database and queue
    init_database(settings.database_path)
    init_queue(max_workers=settings.worker_threads, is_async=settings.async_queue)

    from asu.main import app as real_app

    yield real_app
    
    # Cleanup
    shutdown_queue(wait=False)
    close_database()


@pytest.fixture
def client(app, upstream):
    yield TestClient(app)


@pytest.fixture(scope="session")
def httpserver_listen_address():
    return ("127.0.0.1", 8123)


@pytest.fixture
def upstream(httpserver):
    base_url = ""
    upstream_path = Path("./tests/upstream/")
    expected_file_requests = [
        ".versions.json",
        "releases/1.2.3/.targets.json",
        "releases/1.2.3/targets/testtarget/testsubtarget/profiles.json",
        "releases/23.05.5/.targets.json",
        "releases/23.05.5/targets/ath79/generic/profiles.json",
        "releases/23.05.5/targets/x86/64/profiles.json",
        "snapshots/.targets.json",
        "snapshots/packages/testarch/base/Packages.manifest",
        "snapshots/targets/ath79/generic/profiles.json",
        "snapshots/targets/testtarget/testsubtarget/packages/Packages.manifest",
        "snapshots/targets/testtarget/testsubtarget/profiles.json",
    ]

    for f in expected_file_requests:
        httpserver.expect_request(f"{base_url}/{f}").respond_with_data(
            (upstream_path / f).read_bytes()
        )
