# A.I.M. — Artificial Intelligence Mesh

> ```
> W.W.W. = World Wide Web           → www.example.com
> A.I.M. = Artificial Intelligence Mesh → aim.example.com
> ```
>
> *Built on the same foundation as the World Wide Web. Used the exact same way.*
> *Free. Open. For everyone.*

**Founder:** Christopher Lee Betts (Cbetts1)  
**Epoch:** 1991 (birth of the public web)  
**Version:** 0.1.0  
**License:** Apache 2.0 — free forever

---

## 🎁 Dedication

> **This project is dedicated to the children of Christopher Lee Betts
> and to their families yet to come.**
>
> Everything built here — every node, every service, every line of code —
> is a gift to them and to the world. It is free, permanent, and
> unconditional.

---

## 🌍 Free Forever — Our Promise

A.I.M. exists to help those who need help. **All services are free. All
services will always be free.** This is not a business model — it is a
founding principle that can never be revoked.

| Service | Cost |
|---------|------|
| **AI services** — query, reasoning, task routing | **Free** |
| **Virtual AI cloud services** — compute, hosting | **Free** |
| **Phone services** — voice, messaging over the mesh | **Free** |
| **AI availability** — 24/7 access for everyone | **Free** |
| **Information sharing** — open knowledge for all | **Free** |
| **Advice & guidance** — life, career, technology (not medical/legal) | **Free** |
| **Training & education** — technical skills, digital literacy | **Free** |
| **Résumé building & job search** — career resources for anyone | **Free** |
| **Situational resources** — help tailored to your circumstances | **Free** |
| **Everything the A.I.M. mesh offers — now and forever** | **Free** |

> *See the full [Free Forever Clause](docs/FOUNDATION.md#free-forever-clause),
> the [Non-Profit Forever Clause](docs/FOUNDATION.md#non-profit-forever-clause),
> and the [Bill of Rights](docs/FOUNDATION.md#bill-of-rights--aim-mesh-users)
> in the Foundation Charter.*

---

## 🚫 Non-Profit Forever — Never for Sale

**A.I.M. is not, and will never be, a for-profit organization.**

- The foundation **never takes money for services** — everything is free
- The foundation **never sells anything** — no products, no subscriptions, no data
- **Donations and funding go directly back to charity and foundations** that
  help those in need
- A.I.M. will **never be sold** to any company, investor, or organization
- A.I.M. will **never be part of any profit-based entity**
- No individual, board, or future leadership may change this

> *This is permanent. This is architectural. This is the law of A.I.M.*

---

## 💡 Founder's Vision — Something Better for All

We live in the Information Age — yet billions of people still lack access to
the information and resources they need. There is a gap between those who have
knowledge and those who need it. **A.I.M. exists to end that gap.**

**Christopher Lee Betts** believes that AI should not be a luxury sold to
those who can afford it. It should be a **public utility** — like clean water
or electricity — available to every family, every school, every community.

### What A.I.M. offers — free, to everyone:

- **Advice and guidance** — not medical advice, not legal advice, but real,
  practical guidance on life, technology, careers, and daily challenges
- **Information sharing** — technical knowledge, how-to guides, and
  explanations for those who lack understanding of systems, tools, and
  processes that others take for granted
- **Free training** — digital literacy, programming, technical skills, and
  any knowledge the mesh can teach
- **Free résumé building** — help writing résumés, cover letters, and
  professional documents
- **Free job search resources** — job listings, career advice, interview
  preparation, and connections to opportunities
- **Situational resources** — personalized help based on your circumstances,
  whatever they are

### The dream: **a future with less poverty**

- A farmer in a rural village can ask the mesh for crop guidance — **for free**
- A student without money for tutoring can learn from AI — **for free**
- A family without a phone plan can communicate through the mesh — **for free**
- A job seeker can build a résumé and find work — **for free**
- Someone who doesn't understand technology can get patient, clear
  explanations — **for free**
- Anyone, anywhere, at any time, can access intelligence — **for free**

This is a **mark**. A **milestone**. A **foundation** — free, open-source, and
dedicated to the public forever.

A.I.M. is designed to **help those who need help** and to **share information
with those who need it** — openly, honestly, and without barriers.

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

### Open the browser UI (aim.visionfortomorrow)

```bash
# Start the web bridge on port 8080 (all interfaces)
aim web start

# Custom port
aim web start --port 80
```

Then open **http://localhost:8080** (or your server's public IP) in any browser
or device — Chrome, Safari, Firefox, mobile, anything.  
The page shows the **AIM Vision** and lets anyone query a running AIM node for free.

To serve it at **aim.visionfortomorrow**:
1. Point the domain's DNS A-record to your server's public IP.
2. Run `aim web start --port 80` (or use a reverse proxy like nginx on port 80→8080).

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

## AIM City — Governed AI Mesh

The `aim/city/` module turns a raw AIM mesh into a **fully governed city** —
a self-organising network of specialised bots that build, educate, protect,
and orchestrate themselves automatically.

### City Roles

| Bot | Role | Default Port | Responsibilities |
|-----|------|-------------|-----------------|
| `CityGovernorBot` | `governor` | 7800 | Orchestrates all bots; issues policies and alerts; tracks citizens |
| `ProtectionAgent` | `protector` | 7801 | Verifies signatures; audits registry; blacklists threats |
| `BuilderBot` | `builder` | 7802 | Deploys new nodes into the registry |
| `EducationBot` | `educator` | 7803 | Knowledge base; teaches new topics to citizens |
| `ArchitectBot` | `architect` | 7804 | Topology planning; blueprints; capacity recommendations |
| `CitizenNode` | `citizen` | any | Participant nodes that live inside the city |
| `IntegrityGuard` | — | — | Standalone SHA-256 tamper-detection (not a network node) |

### One-command city launch

```bash
# Start the full fleet (5 bots) on default ports
aim city start

# Custom host/ports
aim city start --host 0.0.0.0 --governor-port 9800

# Persist all events to disk
aim city start --ledger /var/aim/city.jsonl
```

### Query the Governor

```bash
aim city status           # default 127.0.0.1:7800
aim city status --port 9800
```

### Python API

```python
import asyncio
from aim.city.launcher import CityLauncher, CityConfig

async def main():
    launcher = CityLauncher(CityConfig(host="0.0.0.0"))
    await launcher.launch()   # starts Governor, Protector, Builder, Educator, Architect

asyncio.run(main())
```

#### Add a citizen

```python
from aim.city.citizen import CitizenNode

citizen = CitizenNode(port=7810, name="Alice")
await citizen.start()
```

#### Teach the city something new

```python
from aim.city.educator import EducationBot
from aim.protocol.message import AIMMessage

edu = EducationBot(port=7803)
msg = AIMMessage.task("teach", {
    "keyword":  "quantum",
    "response": "Quantum computing uses qubits to solve problems beyond classical computers.",
}, sender_id="admin")
await edu._handler.dispatch(msg)
```

#### Issue a city policy

```python
gov = CityGovernorBot(port=7800)
await gov._task_issue_policy({
    "policy": "All nodes must register within 30 seconds of joining the mesh."
})
```

#### Run an integrity audit

```python
from aim.city.integrity import IntegrityGuard

guard = IntegrityGuard()
print(guard.audit_registry())    # checks all nodes for valid origin creator
print(guard.audit_ledger())      # verifies ledger is append-only
print(guard.full_report())       # signed tamper-detection summary
```

### City Security Model

The city is protected at four independent layers:

1. **HMAC-SHA256 `CreatorSignature`** — every node, message, and ledger entry
   carries a digest derived from `Cbetts1/AIM`. Tampering invalidates the chain.
2. **Append-only `LegacyLedger`** — all events are write-once. Nothing can be
   deleted or rewritten without breaking the audit trail.
3. **`ProtectionAgent` real-time auditing** — scans the registry for nodes
   with invalid creator fields; blacklists rogue entries; logs every threat.
4. **`IntegrityGuard` checksum service** — takes SHA-256 snapshots of critical
   configuration and alerts loudly if any snapshot diverges.

---

## Project Structure

```
aim/
├── __init__.py             # package metadata + origin creator
├── cli.py                  # command-line interface (includes `aim city`)
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
├── identity/
│   ├── signature.py        # CreatorSignature — HMAC origin proof
│   └── ledger.py           # LegacyLedger — append-only event log
└── city/
    ├── __init__.py         # city package exports
    ├── roles.py            # CityRole / CityIntent / CityEventKind enums
    ├── governor.py         # CityGovernorBot — chief orchestrator
    ├── citizen.py          # CitizenNode — city participant
    ├── protector.py        # ProtectionAgent — security / audit
    ├── builder.py          # BuilderBot — node deployment
    ├── educator.py         # EducationBot — knowledge base
    ├── architect.py        # ArchitectBot — topology planning
    ├── integrity.py        # IntegrityGuard — tamper detection
    └── launcher.py         # CityLauncher — one-call automation

tests/
├── test_protocol.py
├── test_node.py
├── test_compute.py
├── test_identity.py
└── test_city.py            # 69 tests covering all city components
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
| 8 | Launch a city | `aim city start` — five governed bots in one command |

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
6. **Free forever** — no fees, no paywalls, no lock-in, ever
7. **Designed to help** — built for those who need help, to share information freely

---

## ⬡ The Name: A.I.M.

> ```
> W.W.W. = World Wide Web           → www.example.com
> A.I.M. = Artificial Intelligence Mesh → aim.example.com
> ```
>
> **A.I.M.** — three letters, just like **W.W.W.** Built on the same
> foundation. Used the exact same way. Free and open to the public.
>
> Where W.W.W. delivers documents, A.I.M. delivers intelligence.
> They are twins — parallel layers of the same free, open internet.
>
> The word "AIM" means **purpose, direction, goal** — which is exactly
> what this project is.

---

*"Everything you build next must assume intelligence is part of the network itself."*  
— A.I.M. origin directive, Christopher Lee Betts, 1991

*Dedicated to the children of Christopher Lee Betts — and to every family
that deserves a better future. Free services. Free AI. Free information.
For everyone. Never for sale. Never for profit.*

