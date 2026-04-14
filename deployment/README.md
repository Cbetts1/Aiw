# AIM Deployment Guide

This directory contains production deployment artefacts for the AIM mesh.

## Files

| File | Purpose |
|---|---|
| `Caddyfile` | Reverse proxy config for [Caddy](https://caddyserver.com) (handles HTTPS automatically) |
| `aim-web.service` | systemd unit for the AIM HTTP/browser gateway (`aim web start`) |
| `aim-node.service` | systemd unit for a standalone AIM node (`aim node start`) |

## Quick start (Ubuntu / Debian)

```bash
# 1. Create a dedicated system user
sudo useradd --system --no-create-home aim

# 2. Create the data directory
sudo mkdir -p /var/lib/aim
sudo chown aim:aim /var/lib/aim

# 3. Install the AIM package (adjust to your setup)
sudo pip install aim  # or: sudo pip install -e /path/to/Aiw

# 4. Copy and enable the web bridge service
sudo cp aim-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aim-web

# 5. (Optional) Copy and enable a node service
sudo cp aim-node.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aim-node

# 6. (Optional) Set up Caddy for HTTPS
#    Edit Caddyfile: replace aim.example.com with your domain
sudo apt install caddy
sudo cp Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

## Configuration

The web bridge reads environment variables:

| Variable | Default | Description |
|---|---|---|
| `AIM_DATA_DIR` | `~/.local/share/aim` | Directory for persistent data (posts, directory, content) |

Set `AIM_DATA_DIR=/var/lib/aim` in the systemd unit's `[Service]` section
(already pre-configured in `aim-web.service`).
