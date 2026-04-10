# AIM — Artificial Intelligence Mesh

> *A parallel AI-native internet layer that runs beside the traditional web.*

**Origin creator:** Cbetts1  
**Epoch:** 1991 (birth of the public web)  
**Version:** 0.1.0

---

## What is AIM?

AIM (Artificial Intelligence Mesh) is a **twin web** — a parallel layer of
intelligence that exists alongside the traditional internet without replacing
it.  Where the web is page-first and request-response, AIM is **agent-first
and conversation-native**.

Every node in AIM is simultaneously a server and an AI agent.  Every
interaction is structured around *intent*, not URLs.  Every entity in the
mesh carries a persistent creator signature that cannot be removed.

```
Traditional Internet          AIM — Artificial Intelligence Mesh
─────────────────────         ──────────────────────────────────
HTTP request/response    ↔    Intent-based AIM message envelope
Static web pages         ↔    Reasoning agent nodes
DNS + routing tables     ↔    NodeRegistry + AI-driven task router
Stateless connections    ↔    Context-aware, memory-sharing nodes
Anonymous packets        ↔    Signed, traceable mesh traffic
```

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    AIM MESH                          │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  4. IDENTITY + LEGACY LAYER                  │   │
│  │     CreatorSignature  ·  LegacyLedger        │   │
│  └──────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────┐   │
│  │  3. AI COMPUTE LAYER                         │   │
│  │     TaskRouter  ·  Executor                  │   │
│  └──────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────┐   │
│  │  2. VIRTUAL NODE LAYER                       │   │
│  │     BaseNode  ·  AgentNode  ·  NodeRegistry  │   │
│  └──────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────┐   │
│  │  1. AIM PROTOCOL LAYER                       │   │
│  │     AIMMessage  ·  Intent  ·  ProtocolHandler│   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### Layer 1 — AIM Protocol Layer (`aim/protocol/`)

AI-native replacement for HTTP.  Messages carry **intent** (QUERY, TASK,
DELEGATE, RESPOND, ANNOUNCE, HEARTBEAT, MEMORY_SET, MEMORY_GET, SPAWN) plus
context and a persistent creator signature.

```python
from aim.protocol.message import AIMMessage, Intent

msg = AIMMessage.query("Summarise the AIM mesh", sender_id="node-a")
# msg.signature == "Cbetts1"  ← always present
```

### Layer 2 — Virtual Node Layer (`aim/node/`)

Each node is a virtual machine acting as both server and agent.  Nodes listen
on a TCP port, accept AIM messages, reason about them, and respond.

```python
from aim.node.agent import AgentNode

node = AgentNode(host="127.0.0.1", port=7700, capabilities=["query", "summarise"])
node.engine.add_rule("aim", "AIM is the Artificial Intelligence Mesh.")
await node.start()
```

### Layer 3 — AI Compute Layer (`aim/compute/`)

Distributed task routing and execution.  The `TaskRouter` finds capable nodes
from the `NodeRegistry` and dispatches work using configurable strategies
(FIRST, ROUND_ROBIN, BROADCAST).  The `Executor` runs named async task
functions with a concurrency limit.

### Layer 4 — Identity + Legacy Layer (`aim/identity/`)

Every node, message, and task carries a `CreatorSignature` — an HMAC-SHA256
digest derived from the origin creator, mesh name, and a unique node nonce.
All events are recorded in an append-only `LegacyLedger` that can persist
to disk.

---

## Quick Start

### Requirements

- Python 3.10+
- No external dependencies for the core mesh

### Install

```bash
pip install -e .
```

### Start a node

```bash
aim node start --host 127.0.0.1 --port 7700
```

### Query a running node

```bash
aim query "What is AIM?" --host 127.0.0.1 --port 7700
```

### Check node liveness

```bash
aim status --host 127.0.0.1 --port 7700
```

### Connect two nodes

```bash
# Terminal 1 — seed node
aim node start --port 7700

# Terminal 2 — second node, announces itself to the seed
aim node start --port 7701 --peers 127.0.0.1:7700
```

---

## Python API

### Start a node programmatically

```python
import asyncio
from aim.node.agent import AgentNode

async def main():
    node = AgentNode(
        host="127.0.0.1",
        port=7700,
        capabilities=["query", "translate"],
    )

    # Add reasoning rules
    node.engine.add_rule("hello", "Hello! I am an AIM agent.")
    node.engine.add_rule("aim",   "AIM is the Artificial Intelligence Mesh.")

    # Register executable tasks
    async def echo(args):
        return args.get("text", "")

    node.register_task("echo", echo)

    await node.start()

asyncio.run(main())
```

### Send a message between nodes

```python
from aim.protocol.message import AIMMessage

msg = AIMMessage.query("What can you do?", sender_id=node_a.node_id)
response = await node_a.send(msg, host="127.0.0.1", port=7701)
print(response.payload["result"])
```

### Route a task through the mesh

```python
from aim.compute.router import TaskRouter, RoutingStrategy
from aim.node.registry import NodeRegistry, NodeRecord

# Register capable nodes
registry = NodeRegistry.default()
registry.register(NodeRecord("worker-1", "127.0.0.1", 7701, ["compute"]))
registry.register(NodeRecord("worker-2", "127.0.0.1", 7702, ["compute"]))

router = TaskRouter(registry=registry, strategy=RoutingStrategy.ROUND_ROBIN)
responses = await router.route("compute", args={"input": "data"}, capability="compute")
```

### Legacy ledger

```python
from aim.identity.ledger import default_ledger, EventKind
from aim.identity.signature import CreatorSignature

sig = CreatorSignature()
ledger = default_ledger()
ledger.record(EventKind.NODE_CREATED, node.node_id, signature=sig)
print(ledger.to_json())
```

---

## Project Structure

```
aim/
├── __init__.py             # package metadata + origin creator
├── cli.py                  # command-line interface
├── protocol/
│   ├── message.py          # AIMMessage envelope + Intent taxonomy
│   └── handler.py          # ProtocolHandler dispatcher
├── node/
│   ├── base.py             # BaseNode — server + basic handlers
│   ├── agent.py            # AgentNode — reasoning, memory, tasks
│   └── registry.py         # NodeRegistry — node discovery
├── compute/
│   ├── router.py           # TaskRouter — mesh-wide task routing
│   └── executor.py         # Executor — local async task runner
└── identity/
    ├── signature.py        # CreatorSignature — HMAC origin proof
    └── ledger.py           # LegacyLedger — append-only event log

tests/
├── test_protocol.py
├── test_node.py
├── test_compute.py
└── test_identity.py
```

---

## Build Path — Zero to Networked System

| Phase | Goal | Command |
|-------|------|---------|
| 0 | Install & verify | `pip install -e . && python -m pytest` |
| 1 | Run first node | `aim node start --port 7700` |
| 2 | Query local node | `aim query "hello" --port 7700` |
| 3 | Two-node mesh | Start node on 7701 with `--peers 127.0.0.1:7700` |
| 4 | Add custom tasks | Register task functions on each node |
| 5 | Distributed routing | Use `TaskRouter` with `NodeRegistry` |
| 6 | Persistent ledger | Pass `persist_path=` to `LegacyLedger` |
| 7 | Cloud deployment | Deploy nodes on VMs, point `--peers` at each other |

---

## Running Tests

```bash
python -m pytest tests/ -v
```

---

## Design Principles

1. **Intelligence is part of the network** — not a service bolted on top
2. **Intent over URL** — every message declares *why*, not just *what*
3. **Every node carries the origin signature** — traceability is architectural
4. **Minimal dependencies** — runs on Termux, a Raspberry Pi, or a cloud VM
5. **Interoperable** — parallel to the web, never dependent on it

---

*"Everything you build next must assume intelligence is part of the network itself."*  
— AIM origin directive, Cbetts1, 1991

