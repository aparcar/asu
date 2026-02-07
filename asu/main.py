import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Union

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from asu import __version__
from asu.branches import get_branches
from asu.config import settings
from asu.routers import api, stats
from asu.util import (
    client_get,
    get_branch,
    is_post_kmod_split_build,
    parse_feeds_conf,
    parse_kernel_version,
    parse_packages_file,
    reload_targets,
    reload_versions,
)

logging.basicConfig(encoding="utf-8", level=settings.log_level)

base_path = Path(__file__).resolve().parent

app = FastAPI()
app.include_router(api.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1")

(settings.public_path / "store").mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=base_path / "static"), name="static")

templates = Jinja2Templates(directory=base_path / "templates")

app.latest = []
app.versions = []
reload_versions(app)
logging.info(f"Found {len(app.versions)} versions")

app.targets = defaultdict(list)
app.profiles = defaultdict(lambda: defaultdict(dict))


@app.api_route("/store/{path:path}", methods=["GET", "HEAD"])
def store(path: str):
    path = (settings.public_path / "store" / path).resolve()
    if not path.is_file() or settings.public_path / "store" not in path.parents:
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=path.name,  # adds Content-Disposition: attachment; filename="..."
        headers={"X-Content-Type-Options": "nosniff"},
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="overview.html",
        context=dict(
            versions=app.versions,
            branches=reversed(get_branches()),
            defaults=settings.allow_defaults,
            version=__version__,
            server_stats=settings.server_stats,
            max_custom_rootfs_size_mb=settings.max_custom_rootfs_size_mb,
            max_defaults_length=settings.max_defaults_length,
        ),
    )


@app.get("/json/v1/{path:path}/index.json")
def json_v1_target_index(path: str) -> dict[str, Union[str, dict[str, str]]]:
    base_path: str = f"{settings.upstream_url}/{path}"
    base_packages: dict[str, str] = parse_packages_file(f"{base_path}/packages")
    if is_post_kmod_split_build(path):
        kmods_directory: str = parse_kernel_version(f"{base_path}/profiles.json")
        if kmods_directory:
            kmod_packages: dict[str, str] = parse_packages_file(
                f"{base_path}/kmods/{kmods_directory}"
            )
            base_packages["packages"].update(kmod_packages.get("packages", {}))
    return base_packages


@app.get("/json/v1/{path:path}/{arch:path}-index.json")
def json_v1_arch_index(path: str, arch: str):
    feed_url: str = f"{settings.upstream_url}/{path}/{arch}"
    feeds: list[str] = parse_feeds_conf(feed_url)
    packages: dict[str, str] = {}
    for feed in feeds:
        packages.update(parse_packages_file(f"{feed_url}/{feed}").get("packages", {}))
    return packages


@app.get("/json/v1/{path:path}/targets/{target:path}/{profile:path}.json")
def json_v1_profile(path: str, target: str, profile: str):
    metadata: dict = client_get(
        f"{settings.upstream_url}/{path}/targets/{target}/profiles.json"
    ).json()
    profiles: dict = metadata.pop("profiles", {})
    if profile not in profiles:
        return {}

    return {
        **metadata,
        **profiles[profile],
        "id": profile,
        "build_at": datetime.utcfromtimestamp(
            int(metadata.get("source_date_epoch", 0))
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }


def generate_latest():
    reload_versions(app)  # Do a reload in case .versions.json has updated.
    return app.latest


@app.get("/json/v1/latest.json")
def json_v1_latest():
    latest = generate_latest()
    return {"latest": latest}


def generate_branches():
    from asu.package_changes import get_revision_changes

    reload_versions(app)  # Do a reload in case .versions.json has updated.
    branches = {k: dict(v) for k, v in get_branches().items()}

    for branch in branches:
        branches[branch]["versions"] = []
        branches[branch]["name"] = branch
        branches[branch]["package_changes"] = get_revision_changes(
            branches[branch].get("branch_off_rev")
        )

    for version in app.versions:
        branch_name = get_branch(version)["name"]
        branches[branch_name]["versions"].append(version)

    for branch in branches:
        version = branches[branch]["versions"][0]
        if not app.targets[version]:
            reload_targets(app, version)

        branches[branch]["targets"] = app.targets[version]

    return branches


@app.get("/json/v1/branches.json")
def json_v1_branches():
    return list(generate_branches().values())


@app.get("/json/v1/overview.json")
def json_v1_overview():
    overview = {
        "latest": generate_latest(),
        "branches": generate_branches(),
        "upstream_url": settings.upstream_url,
        "server": {
            "version": __version__,
            "contact": "mail@aparcar.org",
            "allow_defaults": settings.allow_defaults,
            "repository_allow_list": settings.repository_allow_list,
            "max_custom_rootfs_size_mb": settings.max_custom_rootfs_size_mb,
            "max_defaults_length": settings.max_defaults_length,
        },
    }

    return overview


@app.get("//{path:path}")
def api_double_slash(path: str):
    print(f"Redirecting double slash to single slash: {path}")
    return RedirectResponse(f"/{path}", status_code=301)


# very legacy
@app.get("/overview")
def api_overview():
    return RedirectResponse("/json/v1/overview.json", status_code=301)
