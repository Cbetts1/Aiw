# AIM — Usage Guide

**Artificial Intelligence Mesh** · Free forever · Apache 2.0

---

## Overview

AIM is a parallel AI-native internet layer. Every instance is a virtual node
in a global mesh. Nodes communicate via intent-based messages, form relay
backbones, and expose capabilities to the network.

```
aim <command> [subcommand] [options]
```

---

## Global Options

| Flag | Description |
|------|-------------|
| `--version` | Print version and exit |
| `--verbose` | Enable debug logging |
| `--help` | Show help for any command |

---

## Commands

### `aim node` — Agent node

```sh
# Start a node on the default port (7700)
aim node start

# Start on a specific port with capabilities
aim node start --port 7701 --capabilities "reasoning,search"

# Connect a private node to a public gateway (no port-forwarding needed)
aim node connect-gateway --host gateway.example.com --port 7900
```

Options for `node start`:

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | 127.0.0.1 | Bind address |
| `--port` | 7700 | TCP port |
| `--capabilities` | "" | Comma-separated tags |
| `--verbose` | false | Debug logging |

---

### `aim relay` — Relay backbone node

```sh
# Start a relay
aim relay start --port 7800

# Start with known peer relays
aim relay start --port 7800 --peers 10.0.0.2:7800,10.0.0.3:7800

# Disable message cache
aim relay start --no-cache
```

Options for `relay start`:

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | 0.0.0.0 | Bind address |
| `--port` | 7800 | TCP port |
| `--peers` | "" | Comma-separated host:port peers |
| `--heartbeat-interval` | 30 | Seconds between peer heartbeats |
| `--no-cache` | false | Disable response cache |

---

### `aim gateway` — Public gateway

Allows nodes behind NAT to become reachable on the mesh.

```sh
# Start a gateway
aim gateway start --host 0.0.0.0 --port 7900
```

---

### `aim query` — Query a running node

```sh
aim query "What is the AIM mesh?"
aim query "Tell me about decentralised AI" --host 127.0.0.1 --port 7700
```

---

### `aim status` — Show node status

```sh
aim status
aim status --host 127.0.0.1 --port 7700
```

---

### `aim city` — AI City governance fleet

```sh
# Launch the full 5-bot city fleet
aim city start

# Show city status
aim city status --host 127.0.0.1 --port 7710
```

The city fleet includes:
- **Governor** — chief orchestrator
- **Protector** — security guardian
- **Builder** — infrastructure construction
- **Educator** — knowledge services
- **Architect** — topology planning

---

### `aim web` — HTTP bridge / browser UI

```sh
# Start the web server on port 8080
aim web start

# Custom host and port
aim web start --host 0.0.0.0 --port 8888
```

Endpoints:
- `GET /` — Browser UI
- `GET /health` — Health check
- `GET /api/query?q=TEXT` — Query a node
- `GET /api/status` — Node status
- `GET /api/ans?name=aim://...` — ANS lookup
- `POST /api/content` — Publish content
- `GET /api/content` — List content
- `GET /api/vcloud` — List virtual resources
- `POST /api/vcloud` — Create virtual resource

---

### `aim vcloud` — Virtual cloud resources

```sh
# List all resources
aim vcloud list

# Create a virtual CPU
aim vcloud create vcpu --name "cpu-1" --cores 4 --clock-mhz 2000

# Create a virtual server
aim vcloud create vserver --name "server-1" --vcpus 2 --memory 1024

# Create a virtual cloud region
aim vcloud create vcloud --name "region-west" --region west
```

---

### `aim dns` — DNS ↔ ANS bridge

```sh
# Resolve a hostname or AIM URI
aim dns resolve example.com
aim dns resolve "aim://assistant.ai"

# Register a DNS hostname as an ANS record
aim dns register mynode.example.com --port 7700 --capabilities "reasoning,search"

# List all ANS records
aim dns records
```

---

### `aim health` — Health snapshot

```sh
# Print a JSON health snapshot for the local node
aim health

# Query a remote node's health
aim health --host 127.0.0.1 --port 7700
```

Sample output:

```json
{
  "node_id": "abc123",
  "timestamp": 1714500000.0,
  "status": "healthy",
  "uptime": 3600.0,
  "peer_count": 3,
  "task_count": 12,
  "system": {
    "cpu_count": 8,
    "uptime_seconds": 86400.0,
    "python_version": "3.11.0"
  },
  "errors": []
}
```

---

### `aim cc` — Command Center integration

Connect this node to a remote Command Center for orchestration.

```sh
# Register with a Command Center
aim cc register \
  --cc-host cc.example.com \
  --cc-port 9000 \
  --name "my-node" \
  --repo-url "https://github.com/Cbetts1/Aiw" \
  --capabilities "reasoning,relay"

# Check connection status
aim cc status --cc-host cc.example.com --cc-port 9000
```

The Command Center connection:
- Registers the node's virtual device identity
- Sends heartbeats every 30 seconds
- Accepts remote commands (query, status, shutdown, reload)
- Reports health metrics every 60 seconds
- Reconnects automatically with exponential backoff

---

### `aim build` — Builder engine

Scaffold new modules and scripts programmatically.

```sh
# Build a new AIM module
aim build module mymodule \
  --description "My custom module" \
  --template agent_node \
  --capabilities "search,index"

# List existing modules
aim build list

# Generate a shell script
aim build script deploy --description "Deploy script"

# Generate a JSON config
aim build config myapp --data '{"port": 7750, "region": "local"}'
```

Generated module structure:

```
aim/mymodule/
  __init__.py      ← exports
  node.py          ← AgentNode subclass
  registry.py      ← thread-safe registry
```

---

## `aim mesh` — Full mesh orchestration

```sh
# Bring up the full mesh (node + relay + gateway + city)
aim mesh up

# Join an existing mesh
aim mesh join --relay-host relay.example.com --relay-port 7800

# Show mesh status
aim mesh status

# List known peers
aim mesh peers
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AIM_DATA_DIR` | `~/.local/share/aim` | Runtime data directory |
| `AIM_LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |

---

## Example: Full Termux Setup

```sh
# Install
pkg update && pkg install -y python git
git clone https://github.com/Cbetts1/Aiw.git ~/aim
cd ~/aim && pip install -e .

# Start the web bridge (browse on phone)
aim web start &

# Start a relay node
aim relay start --port 7800 &

# Start an agent node
aim node start --port 7700 &

# Register with Command Center
aim cc register --cc-host cc.example.com --cc-port 9000 \
  --name "my-phone-node" \
  --repo-url "https://github.com/Cbetts1/Aiw" \
  --capabilities "reasoning,relay"
```

---

## See Also

- [INSTALL.md](INSTALL.md) — Installation guide
- [docs/MESH_ARCHITECTURE.md](docs/MESH_ARCHITECTURE.md) — Architecture
- [docs/FOUNDATION.md](docs/FOUNDATION.md) — Project charter
- [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) — Security model
