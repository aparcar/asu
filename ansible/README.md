# ASU Ansible Deployment

Ansible role to deploy the OpenWrt ASU (Attendant Sysupgrade Server) using Podman.

## Features

- Installs Podman and podman-compose
- Creates a non-root `asu` user for running containers
- Deploys ASU microservices architecture from the Git repository
- Configures Caddy reverse proxy with automatic HTTPS
- Configures environment variables
- Sets up systemd service for automatic startup
- Idempotent: running twice automatically rebuilds containers

## Requirements

- Target system: Linux with systemd
- Ansible 2.9+
- Target OS: RHEL/Fedora/CentOS or Debian/Ubuntu (with appropriate package manager)

## Role Variables

Available variables are listed below, along with default values (see `defaults/main.yml`):

```yaml
# User configuration
asu_user: asu
asu_group: asu
asu_home: /home/asu

# Application paths
asu_app_dir: /home/asu/asu
public_path: /var/lib/asu/public

# Domain configuration for Caddy reverse proxy
caddy_domain: ""  # Set to domain for automatic HTTPS (e.g., "sysupgrade.staging.openwrt.org")

# Force rebuild on every run
force_rebuild: true

# Environment variables
allow_defaults: 0
squid_cache: 0
log_level: INFO
upstream_url: https://downloads.openwrt.org
```

## Directory Structure

```
ansible/
├── roles/
│   └── asu-deploy/
│       ├── defaults/
│       │   └── main.yml          # Default variables
│       ├── tasks/
│       │   └── main.yml          # Main tasks
│       ├── handlers/
│       │   └── main.yml          # Handlers for restarts
│       └── templates/
│           ├── env.j2            # .env template
│           └── asu-podman.service.j2  # systemd service
├── playbook.yml                  # Example playbook
└── inventory.ini                 # Inventory file
```

## Usage

1. Edit the inventory file `inventory.ini`:

```ini
[asu_servers]
your-server.example.com ansible_user=root
```

2. Customize variables in `playbook.yml` if needed:

```yaml
- name: Deploy ASU with Podman
  hosts: asu_servers
  become: true
  
  roles:
    - role: asu-deploy
      vars:
        caddy_domain: "sysupgrade.staging.openwrt.org"
        force_rebuild: true
        public_path: /var/lib/asu/public
```

3. Run the playbook:

```bash
cd ansible
ansible-playbook -i inventory.ini playbook.yml
```

## Idempotency and Automatic Rebuilds

The role is designed to automatically rebuild containers when:

- `force_rebuild: true` is set (default)
- The Git repository has updates
- The `.env` file changes

Running the playbook twice will:
1. First run: Install Podman, create user, clone repo, build and start containers
2. Second run: Check for updates, rebuild if needed (due to `force_rebuild: true`)

To disable automatic rebuilds on every run, set `force_rebuild: false` in your playbook.

## Managing the Service

After deployment, the containers are managed by systemd:

```bash
# On the target server
sudo systemctl status asu-podman
sudo systemctl restart asu-podman
sudo systemctl stop asu-podman
sudo systemctl start asu-podman

# Or using podman-compose directly as the asu user
sudo -u asu podman-compose -f /home/asu/asu/podman-compose.yml ps
sudo -u asu podman-compose -f /home/asu/asu/podman-compose.yml logs
```

## Configuring Domain and HTTPS

The role deploys Caddy as a reverse proxy. Configure the domain:

```yaml
roles:
  - role: asu-deploy
    vars:
      caddy_domain: "sysupgrade.staging.openwrt.org"  # Automatic HTTPS
      # caddy_domain: ""  # HTTP only on port 80
```

When a domain is set, Caddy will automatically obtain and manage Let's Encrypt certificates.

## Security Notes

- The `asu` user is created without root privileges
- Containers run in rootless mode under the `asu` user
- Podman socket is user-specific (`/run/user/<uid>/podman/podman.sock`)
- User lingering is enabled to allow services to run without login

## Troubleshooting

Check container logs:
```bash
sudo -u asu podman-compose -f /home/asu/asu/podman-compose.yml logs -f
```

Check systemd service:
```bash
sudo systemctl status asu-podman
sudo journalctl -u asu-podman -f
```

Manual rebuild:
```bash
sudo -u asu bash
cd /home/asu/asu
podman-compose down
podman-compose up -d --build
```
