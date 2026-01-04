# Attendedsysupgrade Server (GSoC 2017)

[![codecov](https://codecov.io/gh/aparcar/asu/branch/master/graph/badge.svg)](https://codecov.io/gh/aparcar/asu)
[![PyPi](https://badge.fury.io/py/asu.svg)](https://badge.fury.io/py/asu)

This project simplifies the sysupgrade process for upgrading the firmware of
devices running OpenWrt or distributions based on it. These tools offer an easy
way to reflash the router with a new firmware version
(including all packages) without the need to use `opkg`.

ASU is based on an [API](#api) to request custom firmware images with any
selection of packages pre-installed. This avoids the need to set up a build
environment, and makes it possible to create a custom firmware image even using
a mobile device.

## Clients of the Sysupgrade Server

### OpenWrt Firmware Selector

Simple web interface using vanilla JavaScript currently developed by @mwarning.
It offers a device search based on model names and show links either to
[official images](https://downloads.openwrt.org/) or requests images via the
_asu_ API. Please join in the development at
[GitLab repository](https://gitlab.com/openwrt/web/firmware-selector-openwrt-org)

- <https://firmware-selector.openwrt.org>

![ofs](misc/ofs.png)

### LuCI app

The package
[`luci-app-attendedsysupgrade`](https://github.com/openwrt/luci/tree/master/applications/luci-app-attendedsysupgrade)
offers a simple tool under `System > Attended Sysupgrade`. It requests a new
firmware image that includes the current set of packages, waits until it's built
and flashes it. If "Keep Configuration" is checked in the GUI, the device
upgrades to the new firmware without any need to re-enter any configuration or
re-install any packages.

![luci](misc/luci.png)

### CLI

With `OpenWrt SNAPSHOT-r26792 or newer` (and in the 24.10 release) the CLI app
[`auc`](https://github.com/openwrt/packages/tree/master/utils/auc) was replaced
with [`owut`](https://openwrt.org/docs/guide-user/installation/sysupgrade.owut)
as a more comprehensive CLI tool to provide an easy way to upgrade your device.

![owut](misc/owut.png)

## Server

The server listens for image requests and, if valid, automatically generates
them. It coordinates several OpenWrt ImageBuilders and caches the resulting
images in a Redis database. If an image is cached, the server can provide it
immediately without rebuilding.

### Active server

> [!NOTE]
> Official server using ImageBuilder published on [OpenWrt
> Downloads](downloads.openwrt.org).

- [sysupgrade.openwrt.org](https://sysupgrade.openwrt.org)

> [!NOTE]
> Unofficial servers, may run modified ImageBuilder

- [ImmortalWrt](https://sysupgrade.kyarucloud.moe)
- [LibreMesh](https://sysupgrade.antennine.org) (only `stable` and `oldstable` OpenWrt versions)
- [sysupgrade.guerra24.net](https://sysupgrade.guerra24.net)
- Create a pull request to add your server here

## Run your own server

For security reasons each build happens inside a container so that one build
can't affect another build. For this to work a Podman container runs an API
service so workers can themselfs execute builds inside containers.

### Installation

The server uses `podman-compose` to manage the containers. On a Debian based
system, install the following packages:

```bash
sudo apt install podman-compose
```

A [Python library](https://podman-py.readthedocs.io/en/latest/) is used to
communicate with Podman over a socket. To enable the socket either `systemd` is
required or the socket must be started manually using the Podman itself:

```bash
# systemd
systemctl --user enable podman.socket
systemctl --user start podman.socket
systemctl --user status podman.socket

# manual (must stay open)
podman system service --time=0 unix:/run/user/$(id -u)/podman/podman.sock
```

Now you can either use the latest ASU containers or build them yourself, run
either of the following two commands:

```bash
# use existing containers
podman-compose pull

# build containers locally
podman-compose build
```

The services are configured via environment variables, which can be set in a
`.env` file

```bash
echo "PUBLIC_PATH=$(pwd)/public" > .env
echo "CONTAINER_SOCKET_PATH=/run/user/$(id -u)/podman/podman.sock" >> .env
# optionally allow custom scripts running on first boot
echo "ALLOW_DEFAULTS=1" >> .env
```

Now it's possible to run all services via `podman-compose`:

```bash
podman-compose up -d
```

This will start the server, the Podman API container and one worker. Once the
server is running, it's possible to request images via the API on
`http://localhost:8000`. Modify `podman-compose.yml` to change the port.

### Production

For production it's recommended to use a reverse proxy like `nginx` or `caddy`.
You can find a Caddy sample configuration in `misc/Caddyfile`.

If you want your server to remain active after you log out of the server, you
must enable "linger" in `loginctl`:

```bash
loginctl enable-linger
```

#### System requirements

- 2 GB RAM (4 GB recommended)
- 2 CPU cores (4 cores recommended)
- 50 GB disk space (200 GB recommended)

#### Squid Cache

Instead of creating and uploading SNAPSHOT ImageBuilder containers everyday,
only a container with installed dependencies and a `setup.sh` script is offered.
ASU will automatically run that script and setup the latest ImageBuilder. To
speed up the process, a Squid cache can be used to store the ImageBuilder
archives locally. To enable the cache, set `SQUID_CACHE=1` in the `.env` file.

To have the cache accessible from running containers, the Squid port 3128 inside
a running container must be forwarded to the host. This can be done by adding
the following line to the `.config/containers/containers.conf` file:

```toml
[network]
pasta_options = [
    "-a", "10.0.2.0",
    "-n", "24",
    "-g", "10.0.2.2",
    "--dns-forward", "10.0.2.3",
    "-T", "3128:3128"
]
```

> If you know a better setup, please create a pull request.

### Development

After cloning this repository, install `uv` which manages the Python
dependencies.

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync --extra dev
```

#### Running the server

```bash
uv run fastapi dev asu/main.py
```

#### Running a worker

```bash
source .env
uv run rq worker
```

### API

The API is documented via _OpenAPI_ and can be viewed interactively on the
server:

- [https://sysupgrade.openwrt.org/docs/](https://sysupgrade.openwrt.org/docs/)
- [https://sysupgrade.openwrt.org/redoc](https://sysupgrade.openwrt.org/redoc/)
