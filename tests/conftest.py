import logging
from pathlib import Path

import pytest
from fakeredis import FakeStrictRedis
from rq import Queue
from fastapi.testclient import TestClient

from asu.config import settings

logger = logging.getLogger(__name__)


def redis_load_mock_data(redis):
    return
    redis.sadd(
        "packages:1.2:1.2.3:testtarget/testsubtarget",
        "test1",
        "test2",
        "test3",
        "valid_new_package",
    )
    redis.sadd("profiles:1.2:1.2.3:testtarget/testsubtarget", "testprofile")
    redis.sadd("profiles:SNAPSHOT:SNAPSHOT:ath79/generic", "tplink_tl-wdr4300-v1")
    redis.sadd("packages:SNAPSHOT:SNAPSHOT:ath79/generic", "vim", "tmux")
    redis.sadd("packages:SNAPSHOT:SNAPSHOT:x86/64", "vim", "tmux")

    redis.sadd("branches", "SNAPSHOT", "1.2", "21.02", "19.07")
    redis.sadd("versions:SNAPSHOT", "SNAPSHOT")
    redis.sadd("versions:1.2", "1.2.3")
    redis.sadd("versions:21.02", "21.02.7", "21.02.0", "21.02.0-rc4", "21.02-SNAPSHOT")
    redis.sadd("versions:19.07", "19.07.7", "19.07.6")

    redis.sadd("profiles:21.02:21.02.7:ath79/generic", "tplink_tl-wdr4300-v1")
    redis.sadd("packages:21.02:21.02.7:ath79/generic", "vim", "tmux")
    redis.sadd("packages:21.02:21.02.7:x86/64", "vim", "tmux")

    redis.sadd("profiles:21.02:21.02.7:x86/64", "generic")
    redis.set("revision:21.02.7:x86/64", "r16847-f8282da11e")

    redis.hset(
        "mapping:1.2:1.2.3:testtarget/testsubtarget",
        mapping={"testvendor,testprofile": "testprofile"},
    )
    redis.hset("targets:1.2", mapping={"testtarget/testsubtarget": "testarch"})
    redis.hset("targets:SNAPSHOT", mapping={"ath79/generic": "", "x86/64": ""})
    redis.hset(
        "targets:21.02",
        mapping={
            "testtarget/testsubtarget": "testarch",
            "ath79/generic": "",
            "x86/64": "",
        },
    )
    redis.hset("mapping-abi", mapping={"test1-1": "test1"})


@pytest.fixture
def redis_server():
    r = FakeStrictRedis()
    redis_load_mock_data(r)
    yield r
    r.flushall()


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
def test_path(tmp_path):
    return str(tmp_path)


@pytest.fixture
def app(redis_server, test_path, monkeypatch, upstream):
    def mocked_redis_client(*args, **kwargs):
        return redis_server

    def mocked_redis_queue():
        return Queue(connection=redis_server, is_async=settings.async_queue)

    saved_upstream_url = settings.upstream_url
    saved_repository_allow_list = settings.repository_allow_list

    settings.public_path = Path(test_path) / "public"
    settings.store_backend = "local"
    settings.async_queue = False
    settings.upstream_url = "http://localhost:8123"
    settings.server_stats = "stats"
    for branch in "1.2", "19.07", "21.02":
        if branch not in settings.branches:
            settings.branches[branch] = {
                "path": "releases/{version}",
                "enabled": True,
            }

    monkeypatch.setattr("asu.util.get_queue", mocked_redis_queue)
    monkeypatch.setattr("asu.routers.api.get_queue", mocked_redis_queue)
    monkeypatch.setattr("asu.util.get_redis_client", mocked_redis_client)

    from asu.main import app as real_app

    yield real_app

    settings.upstream_url = saved_upstream_url
    settings.repository_allow_list = saved_repository_allow_list


class DebugTestClient(TestClient):
    """TestClient that logs response body for error responses."""

    def request(self, *args, **kwargs):
        response = super().request(*args, **kwargs)
        if response.status_code >= 400:
            logger.error("Response %d: %s", response.status_code, response.text)
        return response


@pytest.fixture
def client(app, upstream):
    yield DebugTestClient(app, raise_server_exceptions=True)


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
