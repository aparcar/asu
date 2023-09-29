from os import getenv
from pathlib import Path

import connexion
from flask import Flask, render_template, send_from_directory
from pkg_resources import resource_filename
from rq import Queue
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from yaml import safe_load

from asu import __version__
from asu.common import get_redis_client
from asu.janitor import update


def create_app(test_config: dict = None) -> Flask:
    """Create the main Flask application

    Args:
        test_config (dict): A dictionary containing a configuration during tests

    Returns:
        Flask: The application
    """

    cnxn = connexion.FlaskApp(__name__)
    app = cnxn.app
    app.config.from_mapping(
        PUBLIC_PATH=getenv("PUBLIC_PATH", Path.cwd() / "public"),
        REDIS_URL=getenv("REDIS_URL") or "redis://localhost:6379",
        TESTING=False,
        DEBUG=False,
        UPSTREAM_URL="https://downloads.openwrt.org",
        ALLOW_DEFAULTS=bool(getenv("ALLOW_DEFAULTS", False)),
        ASYNC_QUEUE=True,
        BRANCHES_FILE=getenv("BRANCHES_FILE"),
        MAX_CUSTOM_ROOTFS_SIZE_MB=100,
        REPOSITORY_ALLOW_LIST=[],
    )

    if not test_config:
        for config_file in [
            Path.cwd() / "config.py",
            "/etc/asu/config.py",
        ]:
            if Path(config_file).exists():
                print(f"Loading {config_file}")
                app.config.from_pyfile(config_file)
                break
    else:
        app.config.from_mapping(test_config)

    for option, value in app.config.items():
        if option.endswith("_PATH") and isinstance(value, (Path, str)):
            app.config[option] = Path(value)
            app.config[option].mkdir(parents=True, exist_ok=True)

    if "BRANCHES" not in app.config:
        if app.config["BRANCHES_FILE"] is None:
            app.config["BRANCHES_FILE"] = resource_filename(__name__, "branches.yml")

        with open(app.config["BRANCHES_FILE"], "r") as branches:
            app.config["BRANCHES"] = safe_load(branches)["branches"]

    (Path().cwd()).mkdir(exist_ok=True, parents=True)

    @app.route("/json/")
    @app.route("/json/<path:path>")
    @app.route("/json/v1/<path:path>")
    def json_path(path="index.html"):
        return send_from_directory(app.config["PUBLIC_PATH"] / "json/v1", path)

    @app.route("/store/")
    @app.route("/store/<path:path>")
    def store_path(path="index.html"):
        return send_from_directory(app.config["PUBLIC_PATH"] / "public", path)

    from . import janitor

    app.register_blueprint(janitor.bp)

    from . import api

    app.register_blueprint(api.bp)

    redis_client = get_redis_client(app.config)

    branches = dict(
        map(
            lambda b: (b["name"], b),
            filter(lambda b: b.get("enabled"), app.config["BRANCHES"].values()),
        )
    )

    @app.route("/")
    def overview():
        return render_template(
            "overview.html",
            branches=branches,
            defaults=app.config["ALLOW_DEFAULTS"],
            version=__version__,
        )

    for package, source in app.config.get("MAPPING_ABI", {}).items():
        if not redis_client.hexists("mapping-abi", package):
            redis_client.hset("mapping-abi", package, source)

    cnxn.add_api(
        "openapi.yml",
        arguments={
            "rootfs_size_mb_max": app.config["MAX_CUSTOM_ROOTFS_SIZE_MB"],
        },
        validate_responses=app.config["TESTING"],
    )

    if not app.config["TESTING"]:
        queue = Queue(
            connection=redis_client,
            is_async=app.config["ASYNC_QUEUE"],
        )
        queue.enqueue(
            update,
            {
                "JSON_PATH": app.config["PUBLIC_PATH"] / "json/v1",
                "BRANCHES": app.config["BRANCHES"],
                "UPSTREAM_URL": app.config["UPSTREAM_URL"],
                "ALLOW_DEFAULTS": app.config["ALLOW_DEFAULTS"],
                "REPOSITORY_ALLOW_LIST": app.config["REPOSITORY_ALLOW_LIST"],
                "REDIS_URL": app.config["REDIS_URL"],
            },
            job_timeout="10m",
        )

    return app
