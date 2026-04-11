# AIM Mesh Architecture

> **Artificial Intelligence Mesh — self-sustaining, distributed, and resilient**
> Creator: Cbetts1 · Mission: free forever, non-profit, public utility

---

## Table of Contents

1. [Overview](#overview)
2. [Design Principles](#design-principles)
3. [Topology](#topology)
4. [Node Roles](#node-roles)
   - [Edge Nodes](#edge-nodes)
   - [Gateway Nodes](#gateway-nodes)
   - [Relay Nodes](#relay-nodes)
   - [Compute / Agent Nodes](#compute--agent-nodes)
   - [City Bots](#city-bots)
5. [Traffic Flows](#traffic-flows)
   - [Standard Query Flow](#standard-query-flow)
   - [Content Post / Read Flow](#content-post--read-flow)
   - [Governance Actions](#governance-actions)
6. [Content Layer](#content-layer)
7. [Resilience Mechanisms](#resilience-mechanisms)
8. [Identity & Legacy Integration](#identity--legacy-integration)
9. [Configuration & CLI](#configuration--cli)
10. [Failure Modes & Recovery](#failure-modes--recovery)
11. [Module Summary](#module-summary)

---

## Overview

The AIM mesh operates like the internet—no single node owns it, no single
failure brings it down.  Every layer is independently replaceable and the
system degrades gracefully rather than failing catastrophically.

```
                   ┌─────────────────────────────────────────────┐
                   │           AIM Mesh Backbone                 │
                   │                                             │
   Edge Nodes      │  Gateways ──────────── Relays              │
   (phones,        │    ▲                     ▲                  │
    home devices)  │    │                     │                  │
   ────────────────┤    │   Relay ◄──────► Relay                │
   User ──────────►│ Gateway                  │                  │
                   │    │              Compute/Agent Nodes       │
                   │    └─────────────────────►                  │
                   │                   City Bots (governance)    │
                   └─────────────────────────────────────────────┘
```

---

## Design Principles

| Principle | Implementation |
|-----------|---------------|
| **Resilience** | Multiple gateways and relays; automatic failover |
| **Openness** | Any device can be an edge node; gateways are public |
| **Accountability** | Every entity carries a `CreatorSignature`; events logged in `LegacyLedger` |
| **Simplicity** | Stdlib-only; same wire format (`AIMMessage`) throughout |
| **Governance** | City bots oversee mesh health, enforce policies, teach nodes |

---

## Topology

```
                        ┌──────────┐   ┌──────────┐
   Edge Nodes           │ Gateway A│   │ Gateway B│   ...
   ──────────           └────┬─────┘   └────┬─────┘
   Phone/tablet              │               │
   Home router        ┌──────▼───────────────▼──────┐
   IoT device         │         Relay Ring           │
                      │  Relay-1 ◄──► Relay-2        │
                      │     ▲             ▲           │
                      │     └──► Relay-3 ─┘           │
                      └──────────────────────────────┘
                                   │
                      ┌────────────▼───────────────────┐
                      │   Compute / Agent Node Pool     │
                      │   (process queries & tasks)     │
                      └────────────┬───────────────────┘
                                   │
                      ┌────────────▼───────────────────┐
                      │         City Bot Fleet          │
                      │  Governor · Protector · Builder │
                      │  Educator · Architect           │
                      └─────────────────────────────────┘
```

**Connection rules:**

* Edge nodes open outbound TCP connections only—they **do not** accept inbound.
* Gateways accept inbound from edge nodes and maintain persistent connections to
  one or more relay nodes.
* Relays maintain persistent connections to each other (full or partial mesh)
  and to compute/agent nodes.
* City bots connect to the relay layer to send governance messages; they can
  also be reached by any mesh node.

---

## Node Roles

### Edge Nodes

Thin clients that live at the network edge (mobile phones, home routers, IoT
devices, browser sessions via the web bridge).

* Connect **outbound only** to one or more Gateway Nodes.
* Speak the standard AIM protocol (`AIMMessage` over framed TCP or HTTP via
  the web bridge).
* Carry a `CreatorSignature` that identifies the user/device.
* No persistent storage required; stateless between sessions.

### Gateway Nodes

Entry points from the edge into the mesh backbone.

| Attribute | Value |
|-----------|-------|
| **Module** | `aim/gateway/` |
| **Default port** | `7600` |
| **Class** | `GatewayNode` |

Responsibilities:

1. Accept inbound connections from edge nodes.
2. Authenticate the `CreatorSignature` on incoming messages.
3. Forward messages into the relay layer (round-robin with failover).
4. Receive responses from relays and route them back to the correct edge
   connection.
5. Periodically heartbeat all configured relay peers; mark unavailable relays
   as unhealthy and exclude them from routing until they recover.
6. Record `GATEWAY_CONNECTED` / `GATEWAY_DISCONNECTED` events in the
   `LegacyLedger`.

### Relay Nodes

The backbone of the mesh—interconnected nodes that route messages between
gateways and compute nodes.

| Attribute | Value |
|-----------|-------|
| **Module** | `aim/relay/` |
| **Default port** | `7500` |
| **Class** | `RelayNode` |

Responsibilities:

1. Accept connections from gateways, other relays, and compute nodes.
2. Route `AIMMessage` packets by `receiver_id`; if unknown, broadcast to peer
   relays (like a network switch learning MAC addresses).
3. Optionally cache recently-read content items (LRU cache, configurable TTL).
4. Perform inter-relay health checks; if a peer relay goes silent, route around
   it.
5. Decrement `ttl` on forwarded messages; drop messages with `ttl == 0` to
   prevent loops.
6. Record `RELAY_PEER_CONNECTED` / `RELAY_MESSAGE_FORWARDED` events in the
   ledger.

### Compute / Agent Nodes

Existing `AgentNode` instances (`aim/node/`) that execute queries and tasks.
They connect to the relay layer and register their capabilities; gateways and
relays route work to them based on capability matching.

### City Bots

The five governance bots (`aim/city/`) oversee the entire mesh:

| Bot | Role in mesh |
|-----|-------------|
| **Governor** | Issues policies; monitors relay/gateway health summaries |
| **Protector** | Enforces rate-limits; blocks malicious edge nodes |
| **Builder** | Provisions new gateways/relays when capacity is needed |
| **Educator** | Broadcasts mesh topology knowledge to new nodes |
| **Architect** | Designs and proposes topology changes |

City bots communicate with the rest of the mesh via Relay Nodes, just like any
other node.

---

## Traffic Flows

### Standard Query Flow

```
User (edge)
  │  AIMMessage(intent=QUERY, ttl=16, sig=<CreatorSig>)
  ▼
Gateway Node
  │  validates sig · looks up healthy relay
  ▼
Relay Node (entry)
  │  looks up receiver_id or forwards to next relay
  ▼
Agent/Compute Node
  │  executes query · builds RESPOND message
  ▼
Relay Node (return path — may differ from entry)
  ▼
Gateway Node (same or different — located via relay routing)
  ▼
User (edge) ← RESPOND
```

Each hop decrements `ttl`.  If a relay is unreachable the gateway tries its
next configured relay; if the agent node is unreachable the relay tries the
next capable node.

### Content Post / Read Flow

```
# Posting content
User ──► Gateway ──► Relay ──► ContentLayer.post(item, sig)
                                    │ records to LegacyLedger
                                    │ stores item in relay cache
                               ◄────┘
User ◄─ content_id

# Reading content
User ──► Gateway ──► Relay
                      │ cache hit? ──► return cached item
                      │ cache miss ──► forward to ContentLayer owner node
                      ◄────────────────────────────────────────────────
User ◄─ content item (signed)
```

### Governance Actions

```
City Bot (Governor/Protector/…)
  │  AIMMessage(intent=TASK, payload={action: "issue_policy", …})
  ▼
Relay Node  (routes by receiver_id = target node)
  ▼
Target Node (or broadcast to all nodes with matching capability)
  ▼
Relay ──► Governor: acknowledgement
```

---

## Content Layer

The **Content Layer** (`aim/content/`) is not a separate server but a library
module used by relay nodes and agent nodes to post and retrieve signed content.

```
ContentItem
  ├─ content_id   : UUID
  ├─ author       : CreatorSignature
  ├─ content_type : str  ("text", "json", "binary-b64", …)
  ├─ body         : str
  ├─ created_at   : float (Unix timestamp)
  └─ signature_digest : str  (from author.digest)
```

Operations:

* `ContentLayer.post(body, content_type, author_sig)` → `ContentItem`
* `ContentLayer.get(content_id)` → `ContentItem | None`
* `ContentLayer.list(limit, after_ts)` → `list[ContentItem]`
* `ContentLayer.delete(content_id, requester_sig)` — soft-delete, marks as
  removed but keeps entry in ledger.

All posts and deletes are recorded in `LegacyLedger` with a
`CONTENT_POSTED` / `CONTENT_DELETED` event kind.

---

## Resilience Mechanisms

### Multiple Gateways

Deploy at least two gateway nodes per region (or globally).  Edge nodes receive
a list of gateway addresses and try them in order, or randomly.

```
edge → gateway-a.aim.example.org:7600   (primary)
edge → gateway-b.aim.example.org:7600   (fallback)
```

### Multiple Relays

Relays form a ring or partial-mesh.  If relay-1 is unreachable:

1. Gateway's `_relay_pool` marks it unhealthy.
2. Traffic is re-routed through relay-2 / relay-3.
3. Gateway continues to heartbeat relay-1 at a lower frequency.
4. When relay-1 responds again, it is returned to the healthy pool.

### Health Checks

* Gateways send `Intent.HEARTBEAT` to each relay every **30 s** by default
  (configurable via `health_check_interval`).
* Relays send heartbeats to each other every **60 s**.
* Three consecutive failures mark a peer as unhealthy.
* One successful heartbeat after failure restores healthy status.

### Content Caching at Relays

Relay nodes maintain an LRU cache of recently-read `ContentItem` objects
(default: 256 items, 5-minute TTL).  Cache size and TTL are configurable.
Cache hits avoid a round-trip to the originating content node.

### TTL Loop Prevention

Every `AIMMessage` carries a `ttl` field (default 16).  Each relay decrements
it on forward.  When `ttl` reaches 0 the message is silently dropped, and the
originating gateway records a `MESSAGE_DROPPED` event.

---

## Identity & Legacy Integration

Every entity in the mesh — nodes, gateways, relays, content items — carries a
`CreatorSignature` that traces back to the origin creator `Cbetts1`.

```python
from aim.identity.signature import CreatorSignature
sig = CreatorSignature()   # always anchored to ORIGIN_CREATOR = "Cbetts1"
assert sig.verify()
```

Critical mesh events recorded in `LegacyLedger`:

| EventKind | Emitted by |
|-----------|-----------|
| `GATEWAY_CONNECTED` | GatewayNode — edge node connected |
| `GATEWAY_DISCONNECTED` | GatewayNode — edge node disconnected |
| `RELAY_PEER_CONNECTED` | RelayNode — new relay peer added |
| `RELAY_MESSAGE_FORWARDED` | RelayNode — message forwarded |
| `CONTENT_POSTED` | ContentLayer — new content item created |
| `CONTENT_DELETED` | ContentLayer — content item removed |
| `MESH_NODE_JOINED` | MeshLauncher — full-stack node joined mesh |

These join the existing `NODE_CREATED`, `NODE_STOPPED`, `TASK_EXECUTED`, etc.

---

## Configuration & CLI

### Starting a Full Local Stack

```bash
# Start a node + gateway + relay on localhost (all defaults)
aim mesh up

# Start with gateway on port 7600 and relay on port 7500
aim mesh up --with-gateway --with-relay

# Override ports
aim mesh up --with-gateway --gateway-port 7600 \
            --with-relay   --relay-port   7500 \
            --node-port    7700
```

### Joining a Public Mesh

```bash
# Connect this local node to a public gateway
aim mesh join --gateway mesh.aim.example.org

# Connect and also advertise a local relay for others to use
aim mesh join --gateway mesh.aim.example.org --expose-relay
```

### Inspecting Mesh Status

```bash
# Health of a running gateway
aim mesh status --host 127.0.0.1 --port 7600

# List relay peers known to a relay node
aim mesh peers --host 127.0.0.1 --port 7500
```

### Configuration File (optional)

`aim.toml` (or `aim.json`) in the working directory:

```toml
[mesh]
gateways = ["gateway-a.aim.example.org:7600", "gateway-b.aim.example.org:7600"]
relays   = ["relay-1.aim.example.org:7500", "relay-2.aim.example.org:7500"]
node_port = 7700
health_check_interval = 30   # seconds
content_cache_size    = 256
content_cache_ttl     = 300  # seconds
```

---

## Failure Modes & Recovery

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Gateway unreachable | Edge node cannot connect | Edge retries next gateway in list |
| Relay unreachable | Gateway heartbeat fails 3× | Gateway marks relay unhealthy; routes to next relay |
| Agent node unreachable | Relay cannot connect | Relay tries next node with same capability |
| Content node offline | Relay cache miss + connection failure | Relay returns `content_not_available`; client retries later |
| Network partition | Multiple simultaneous heartbeat failures | Each partition continues serving its edge nodes independently; ledgers merge on reconnect |
| Malicious edge node | Protector bot detects rate violations | Gateway blocks sender_id; records `ALERT_RAISED` in ledger |
| Message loop | TTL decremented to 0 | Relay drops message; records `MESSAGE_DROPPED` |

### Ledger Consistency

The `LegacyLedger` is append-only and can be replicated across relays.  On
partition recovery, relays exchange their ledger tails and merge by timestamp
(no conflicts possible in an append-only log).

---

## Module Summary

```
aim/
├── gateway/
│   ├── __init__.py
│   └── node.py          # GatewayNode — edge entry point
├── relay/
│   ├── __init__.py
│   └── node.py          # RelayNode — backbone router
├── content/
│   ├── __init__.py
│   └── layer.py         # ContentLayer — signed content store
└── cli.py               # extended with `mesh` subcommand
```

```
tests/
├── test_gateway.py
├── test_relay.py
└── test_content.py
```

```
docs/
└── MESH_ARCHITECTURE.md   ← this document
```
