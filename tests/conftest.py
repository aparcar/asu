import shutil
import tempfile
from pathlib import Path

import prometheus_client
import pytest
from fakeredis import FakeStrictRedis
from pytest import MonkeyPatch

from asu.asu import create_app


def redis_load_mock_data(redis):
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

    redis.sadd("profiles:21.02:21.02.7:ath79/generic", "tplink_tl-wdr4300-v1")
    redis.sadd("packages:21.02:21.02.7:ath79/generic", "vim", "tmux")
    redis.sadd("packages:21.02:21.02.7:x86/64", "vim", "tmux")

    redis.hset(
        "mapping:1.2:1.2.3:testtarget/testsubtarget",
        mapping={"testvendor,testprofile": "testprofile"},
    )
    redis.sadd("targets:1.2", "testtarget/testsubtarget")
    redis.sadd("targets:SNAPSHOT", "ath79/generic", "x86/64")
    redis.sadd("targets:21.02", "testtarget/testsubtarget", "ath79/generic", "x86/64")
    redis.hset("mapping-abi", mapping={"test1-1": "test1"})


@pytest.fixture
def redis_server():
    r = FakeStrictRedis()
    redis_load_mock_data(r)
    yield r
    r.flushall()


@pytest.fixture
def mocked_redis(monkeypatch, redis_server):
    def mocked_redis_client(*args, **kwargs):
        return redis_server

    monkeypatch.setattr("asu.common.get_redis_client", mocked_redis_client)
    monkeypatch.setattr("asu.janitor.get_redis_client", mocked_redis_client)
    monkeypatch.setattr("asu.api.get_redis_client", mocked_redis_client)
    monkeypatch.setattr("asu.asu.get_redis_client", mocked_redis_client)


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
def app(mocked_redis, test_path):
    mock_app = create_app(
        {
            "ASYNC_QUEUE": False,
            "PUBLIC_PATH": test_path,
            "REDIS_URL": "foobar",
            "CACHE_PATH": test_path,
            "TESTING": True,
            "UPSTREAM_URL": "http://localhost:8001",
            "REPOSITORY_ALLOW_LIST": [],
            "BRANCHES": {
                "SNAPSHOT": {
                    "name": "SNAPSHOT",
                    "updates": "dev",
                    "enabled": True,
                    "snapshot": True,
                    "versions": ["SNAPSHOT"],
                    "git_branch": "master",
                    "path": "snapshots",
                    "path_packages": "snapshots/packages",
                    "pubkey": "RWS1BD5w+adc3j2Hqg9+b66CvLR7NlHbsj7wjNVj0XGt/othDgIAOJS+",
                    "repos": ["base", "packages", "luci", "routing", "telephony"],
                    "extra_repos": {},
                    "extra_keys": [],
                },
                "1.2": {
                    "name": "1.2",
                    "enabled": True,
                    "snapshot": True,
                    "versions": ["1.2.3"],
                    "git_branch": "master",
                    "path": "snapshots",
                    "path_packages": "snapshots/packages",
                    "repos": ["base"],
                    "pubkey": "RWRqylWEtrAZQ9hlSSEkqCJD4SAFswJQR1yoMfD3mzO3TEnY7LGthxPi",
                    "updates": "dev",
                    "targets": {
                        "testtarget/testsubtarget": "testarch",
                        "x86/64": "x86_64",
                    },
                    "package_changes": {
                        "package_to_remove": None,
                        "package_to_replace": "valid_new_package",
                    },
                },
                "21.02": {
                    "name": "21.02",
                    "enabled": True,
                    "snapshot": True,
                    "versions": ["21.02.7", "21.02.0", "21.02.0-rc4", "21.02-SNAPSHOT"],
                    "git_branch": "openwrt-21.02",
                    "path": "releases/{version}",
                    "path_packages": "releases/packages-{branch}",
                    "repos": ["base"],
                    "pubkey": "RWRqylWEtrAZQ9hlSSEkqCJD4SAFswJQR1yoMfD3mzO3TEnY7LGthxPi",
                    "updates": "rc",
                    "targets": {"testtarget/testsubtarget": "testarch"},
                },
                "19.07": {
                    "name": "19.07",
                    "enabled": True,
                    "versions": ["19.07.7", "19.07.6"],
                    "git_branch": "openwrt-19.07",
                    "path": "releases/{version}",
                    "path_packages": "releases/packages-{branch}",
                    "repos": ["base"],
                    "pubkey": "RWRqylWEtrAZQ9hlSSEkqCJD4SAFswJQR1yoMfD3mzO3TEnY7LGthxPi",
                    "updates": "stable",
                    "targets": {"testtarget/testsubtarget": "testarch"},
                },
            },
        }
    )

    return mock_app


@pytest.fixture
def app_using_branches_yml(mocked_redis, test_path):
    mock_app = create_app(
        {
            "ASYNC_QUEUE": False,
            "PUBLIC_PATH": test_path,
            "CACHE_PATH": test_path,
            "TESTING": True,
            "UPSTREAM_URL": "http://localhost:8001",
            "BRANCHES_FILE": "./asu/branches.yml",
        }
    )

    return mock_app


@pytest.fixture
def app_using_default_branches(mocked_redis, test_path):
    mock_app = create_app(
        {
            "ASYNC_QUEUE": False,
            "PUBLIC_PATH": test_path,
            "CACHE_PATH": test_path,
            "TESTING": True,
            "UPSTREAM_URL": "http://localhost:8001",
        }
    )

    return mock_app


@pytest.fixture
def client(mocked_redis, app):
    return app.test_client()


@pytest.fixture(scope="session")
def httpserver_listen_address():
    return ("127.0.0.1", 8001)
