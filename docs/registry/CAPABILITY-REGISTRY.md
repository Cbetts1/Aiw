# AIM Node Capability Registry

**Maintainer:** AIM Foundation Protocol Working Group  
**Version:** 1.0 — 2026

This registry lists standardised **capability tags** that AIM nodes may
advertise in their `NodeRecord.capabilities` list and `ANNOUNCE` messages.

Capability tags tell the `TaskRouter` what a node can do, enabling intelligent
routing without prior knowledge of individual nodes.

---

## Registered Capabilities

| Tag            | RFC            | Status    | Description |
|----------------|----------------|-----------|-------------|
| `query`        | AIM-RFC-0001   | PERMANENT | Node accepts `QUERY` intent messages |
| `task`         | AIM-RFC-0001   | PERMANENT | Node accepts `TASK` intent messages |
| `compute`      | AIM-RFC-0001   | STABLE    | Node performs general computational tasks |
| `summarise`    | AIM-RFC-0001   | STABLE    | Node can summarise text or data |
| `translate`    | AIM-RFC-0001   | STABLE    | Node can translate between languages |
| `memory`       | AIM-RFC-0001   | STABLE    | Node supports `MEMORY_SET` / `MEMORY_GET` intents |
| `spawn`        | AIM-RFC-0001   | STABLE    | Node can spawn child nodes |
| `governor`     | AIM City       | STABLE    | AIM City governor role |
| `protector`    | AIM City       | STABLE    | AIM City protector (security auditor) role |
| `builder`      | AIM City       | STABLE    | AIM City node deployment role |
| `educator`     | AIM City       | STABLE    | AIM City knowledge-base role |
| `architect`    | AIM City       | STABLE    | AIM City topology-planning role |
| `citizen`      | AIM City       | STABLE    | AIM City participant node |
| `gateway`      | AIM-RFC-0003   | STABLE    | HTTP↔AIM bridge gateway |
| `ans-resolver` | AIM-RFC-0003   | STABLE    | AIM Name Service resolver |
| `seed`         | AIM-RFC-0003   | PERMANENT | Public seed node for peer bootstrapping |

---

## Capability Status Definitions

See [INTENT-REGISTRY.md](INTENT-REGISTRY.md) for status definitions. The same
status taxonomy applies to capabilities.

---

## Registering a New Capability

### Standard capabilities (no vendor prefix)

1. Open a GitHub Discussion: `[RFC] New Capability: <tag>`.
2. Follow the RFC process. Upon acceptance the tag will be added here.

### Vendor or community capabilities

Use a reverse-DNS prefix separated by a colon:

```
com.example:search
org.myproject:vector-store
```

Vendor-prefixed capabilities do not require RFC registration. Add a row to
the table below via pull request.

---

## Vendor / Community Capabilities

| Tag (prefixed)          | Registrant     | Description |
|-------------------------|----------------|-------------|
| *(none registered yet)* | —              | — |

---

## Capability Routing Rules

The `TaskRouter` (see `aim/compute/router.py`) uses capability tags to find
capable nodes:

1. **FIRST** strategy — routes to the first node advertising the required capability.
2. **ROUND_ROBIN** strategy — cycles through all capable nodes evenly.
3. **BROADCAST** strategy — sends to all capable nodes simultaneously.

When `find_by_capability(tag)` returns an empty list, the router MUST return
an appropriate error rather than silently dropping the task.
