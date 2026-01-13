# Package Changes Service

A Python microservice for handling OpenWrt package transformations based on version, target, and profile.

## Features

- 🔄 **YAML Configuration** - Easy-to-edit transformation rules
- 🔥 **Hot Reload** - Automatically reloads when config file changes
- 🚀 **FastAPI** - Modern async Python web framework
- 📦 **Version Transitions** - Handle package changes between versions
- 🎯 **Profile-Specific** - Add packages based on device profile
- ⚠️ **Deprecation Warnings** - Alert on deprecated packages

## Installation

```bash
cd package-changes-service
poetry install
```

## Running

```bash
poetry run python main.py
# Or: uvicorn main:app --host 0.0.0.0 --port 8081
```

## API Usage

**POST /apply** - Transform package list

```json
{
  "from_version": "22.03.5",
  "version": "23.05.0",
  "target": "ath79/generic",
  "profile": "tplink_archer-c7-v5",
  "packages": ["luci", "firewall", "iptables"]
}
```

Response includes transformed packages, warnings, and applied transformations.

## Configuration

Edit `package_changes.yaml` to define transformation rules. The service automatically reloads when the file is modified.

See the YAML file for examples of:
- Package renames
- Version transitions
- Profile-specific packages
- Custom transformation rules
- Conflict resolution

## Integration

Configure the Go builder to use this service:

```yaml
package_changes_url: "http://localhost:8081"
```
