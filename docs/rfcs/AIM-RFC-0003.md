# AIM-RFC-0003 — NodeRegistry & Peer Discovery

| Field       | Value                                         |
|-------------|-----------------------------------------------|
| Number      | AIM-RFC-0003                                  |
| Title       | NodeRegistry, Peer Discovery & AIM Name Service |
| Author(s)   | Cbetts1 (AIM Foundation)                      |
| Status      | FINAL                                         |
| Created     | 2026-04-11                                    |
| Updated     | 2026-04-11                                    |
| Supersedes  | —                                             |
| Superseded  | —                                             |

---

## Abstract

This document specifies how AIM nodes discover and track one another. It
defines the `NodeRegistry` (in-process peer store), the `ANNOUNCE` handshake
protocol, seed-node bootstrapping, and the **AIM Name Service (ANS)** — a
DNS-analogue that maps human-readable names (e.g. `aim://weather.public.aim`)
to `NodeRecord` addresses.

---

## 1. Motivation

Nodes need to find each other. The Web solves this with DNS + IP routing. AIM
solves it with a layered approach:

1. **NodeRegistry** — an in-process or network-shared store of known node
   addresses and capabilities.
2. **ANNOUNCE handshake** — a lightweight gossip protocol for nodes to
   introduce themselves to peers.
3. **Seed nodes** — well-known public nodes that act as entry points into the
   mesh (analogous to DNS root servers).
4. **AIM Name Service (ANS)** — human-readable names that resolve to
   `NodeRecord` entries, enabling `aim://` URIs.

---

## 2. Specification

### 2.1 NodeRecord

A `NodeRecord` is the fundamental unit of peer information.

| Field          | Type         | Required | Description |
|----------------|--------------|----------|-------------|
| `node_id`      | string       | MUST     | UUID v4 |
| `host`         | string       | MUST     | IPv4, IPv6, or hostname |
| `port`         | integer      | MUST     | TCP port (1–65535) |
| `capabilities` | list[string] | SHOULD   | Registered capability tags |
| `creator`      | string       | MUST     | Origin creator identifier |
| `public_key`   | string       | MAY      | Ed25519 public key (base64url) |
| `metadata`     | object       | MAY      | Arbitrary key-value pairs |

### 2.2 NodeRegistry Operations

A conformant `NodeRegistry` implementation MUST support:

| Operation               | Signature | Description |
|-------------------------|-----------|-------------|
| `register(record)`      | NodeRecord → void | Add or update a node record |
| `deregister(node_id)`   | str → void | Remove a node record |
| `get(node_id)`          | str → NodeRecord? | Look up a specific node |
| `all_nodes()`           | → list[NodeRecord] | Return all known nodes |
| `find_by_capability(c)` | str → list[NodeRecord] | Filter by capability tag |
| `count()`               | → int | Number of registered nodes |

All operations MUST be thread-safe.

### 2.3 ANNOUNCE Handshake

When a new node joins the mesh it MUST send an `ANNOUNCE` message to each
configured seed peer:

```json
{
  "intent": "announce",
  "payload": { "capabilities": ["query", "task"] },
  "sender_id": "<node_id>",
  "signature": "Cbetts1"
}
```

Upon receiving an `ANNOUNCE`, a node:

1. MUST add the sender to its local `NodeRegistry`.
2. SHOULD reply with its own `ANNOUNCE` message so the new node learns about
   the receiving node.
3. MAY forward the `ANNOUNCE` to other known peers (gossip propagation), but
   MUST decrement `ttl` before doing so.

### 2.4 Seed Nodes

Seed nodes are well-known public AIM nodes operated by the AIM Foundation.
They act as entry points for new nodes joining the mesh.

The reference implementation ships with the following default seed nodes
(subject to change; check the AIM Foundation website for the current list):

```
seed-us.aim-mesh.org:7700
seed-eu.aim-mesh.org:7700
seed-ap.aim-mesh.org:7700
```

New nodes SHOULD contact at least one seed node on startup. Seed nodes MUST
NOT be used as general-purpose routing hubs; they exist solely to bootstrap
peer discovery.

### 2.5 AIM Name Service (ANS)

The AIM Name Service maps human-readable names to `NodeRecord` entries,
enabling `aim://` URIs.

#### 2.5.1 ANS Name Format

```
aim://<name>.<zone>
```

Examples:
- `aim://weather.public.aim`
- `aim://assistant.mycompany.aim`
- `aim://gateway.seed.aim`

Rules:
- Names are case-insensitive and MUST be normalised to lowercase.
- Names MUST contain only ASCII letters, digits, and hyphens within each
  label, separated by dots.
- Each label MUST be 1–63 characters; total name length MUST NOT exceed 253
  characters.

#### 2.5.2 ANSRecord

| Field          | Type         | Required | Description |
|----------------|--------------|----------|-------------|
| `name`         | string       | MUST     | Normalised ANS name |
| `node_id`      | string       | MUST     | Target node UUID |
| `host`         | string       | MUST     | Target host |
| `port`         | integer      | MUST     | Target port |
| `capabilities` | list[string] | SHOULD   | Capability tags |
| `creator`      | string       | MUST     | Origin creator identifier |
| `registered_at`| float        | MUST     | Unix timestamp of registration |
| `ttl_seconds`  | integer      | SHOULD   | Cache TTL (default 3600) |

#### 2.5.3 ANS Resolution Algorithm

1. Normalise the name to lowercase.
2. Check the local `ANSRegistry` cache; if a non-expired entry exists, return it.
3. If not found locally, query the nearest ANS resolver node
   (`aim://resolver.seed.aim` or a locally configured resolver).
4. Resolver responds with an `ANSRecord` or `null` (not found).
5. Cache the result for `ttl_seconds`.

#### 2.5.4 ANS Registration

Names MAY be registered free of charge via the public ANS resolver operated
by the AIM Foundation. Registration requires:

- A valid `NodeRecord` with a reachable `host:port`.
- The `creator` field matching the registrant's identity.
- Compliance with the AIM Abuse Policy.

---

## 3. Backwards Compatibility

ANS is an entirely new subsystem; existing code that does not use ANS is
unaffected. The `ANNOUNCE` handshake is already implemented in the reference
codebase and this RFC formalises its behaviour without changing it.

---

## 4. Security Considerations

- **Registry poisoning**: A malicious node SHOULD NOT be able to overwrite a
  legitimate node's record. Implementations SHOULD verify the `CreatorSignature`
  before accepting an `ANNOUNCE` from an unknown sender.
- **ANS spoofing**: ANS resolvers MUST validate Ed25519 signatures on ANS
  records to prevent name hijacking (once PKI is deployed per AIM-RFC-0002).
- **Sybil attacks**: A single entity controlling many node IDs can manipulate
  routing. The `ProtectionAgent` (AIM City) monitors for this pattern.

---

## 5. Reference Implementation

- `aim/node/registry.py` — `NodeRegistry`, `NodeRecord`
- `aim/ans/registry.py` — `ANSRegistry`, `ANSRecord`
- `aim/ans/resolver.py` — `ANSResolver`

---

## 6. Changelog

| Date       | Author    | Change |
|------------|-----------|--------|
| 2026-04-11 | Cbetts1   | Initial FINAL specification |
