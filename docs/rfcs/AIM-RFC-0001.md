# AIM-RFC-0001 — Core Protocol Specification

| Field       | Value                                          |
|-------------|------------------------------------------------|
| Number      | AIM-RFC-0001                                   |
| Title       | AIM Core Protocol — Message Envelope & Intent  |
| Author(s)   | Cbetts1 (AIM Foundation)                       |
| Status      | FINAL                                          |
| Created     | 2026-04-11                                     |
| Updated     | 2026-04-11                                     |
| Supersedes  | —                                              |
| Superseded  | —                                              |

---

## Abstract

This document specifies the AIM (Artificial Intelligence Mesh) core protocol:
the wire-format of an `AIMMessage` envelope, the normative set of `Intent`
types, the `Status` taxonomy for responses, and the rules governing message
routing through the mesh. Conformant implementations in any language MUST
follow this specification to be considered AIM-compatible.

---

## 1. Motivation

The World Wide Web is built on HTTP — a request/response protocol designed for
serving static documents. AIM is designed for a world where every participant
is a reasoning agent. The core protocol therefore carries **intent** (the
semantic purpose of a message) rather than a resource path, enabling every
node to reason about incoming traffic without parsing application-level
conventions.

---

## 2. Specification

### 2.1 Wire Format

AIM messages are encoded as UTF-8 JSON objects preceded by a 4-byte
big-endian unsigned integer that specifies the length of the JSON payload in
bytes.

```
┌────────────────────────────────┐
│  Length prefix (4 bytes, BE)   │
├────────────────────────────────┤
│  JSON payload (length bytes)   │
└────────────────────────────────┘
```

The JSON object MUST contain the following fields:

| Field            | Type                | Required | Description |
|------------------|---------------------|----------|-------------|
| `intent`         | string (Intent)     | MUST     | Semantic purpose |
| `payload`        | object              | MUST     | Intent-specific data |
| `sender_id`      | string              | MUST     | Originating node ID |
| `receiver_id`    | string \| null      | SHOULD   | Target node ID; null = broadcast |
| `message_id`     | string (UUID v4)    | MUST     | Globally unique message identifier |
| `correlation_id` | string \| null      | SHOULD   | Links RESPOND to originating message |
| `timestamp`      | number (Unix epoch) | MUST     | Seconds since 1970-01-01T00:00:00Z |
| `context`        | object              | SHOULD   | Session/conversation context |
| `signature`      | string              | MUST     | Origin creator identifier |
| `ttl`            | integer (≥0)        | MUST     | Hops remaining; MUST be decremented at each relay |

Unknown fields MUST be preserved by relay nodes and MUST NOT cause parse
failures in conformant implementations.

### 2.2 Intent Types

The `intent` field MUST be one of the following registered values. All values
are lowercase ASCII strings.

| Intent        | Direction | Description |
|---------------|-----------|-------------|
| `query`       | →         | Request information or a reasoning response |
| `task`        | →         | Delegate an executable unit of work |
| `delegate`    | →         | Forward a task to another node |
| `respond`     | ←         | Reply to a prior message |
| `announce`    | →/←       | Broadcast node presence and capabilities |
| `heartbeat`   | →/←       | Liveness probe |
| `memory_set`  | →         | Write a key-value pair to shared mesh memory |
| `memory_get`  | →         | Read a key-value pair from shared mesh memory |
| `spawn`       | →         | Request creation of a child node |

New intent types MUST be registered via the RFC process (see
[AIM Intent Registry](../registry/INTENT-REGISTRY.md)).

### 2.3 Intent-Specific Payload Schemas

#### `query`
```json
{ "text": "<string — the question or query>" }
```

#### `task`
```json
{ "name": "<string — task identifier>", "args": { "<key>": "<value>" } }
```

#### `delegate`
```json
{
  "original_message_id": "<UUID>",
  "target_node": "<node_id>",
  "args": {}
}
```

#### `respond`
```json
{ "result": "<any JSON-serialisable value>", "status": "<Status>" }
```

#### `announce`
```json
{ "capabilities": ["<string>", "…"] }
```

#### `heartbeat`
```json
{}
```

#### `memory_set`
```json
{ "key": "<string>", "value": "<any JSON-serialisable value>", "scope": "<string — optional namespace>" }
```

#### `memory_get`
```json
{ "key": "<string>", "scope": "<string — optional namespace>" }
```

#### `spawn`
```json
{ "capabilities": ["<string>"], "host": "<string — optional>", "port": "<integer — optional>" }
```

### 2.4 Status Values

The `status` field within a `respond` payload MUST be one of:

| Status      | Meaning |
|-------------|---------|
| `ok`        | Request completed successfully |
| `error`     | Request failed; payload MAY contain an `error` string field |
| `pending`   | Work is in progress; a subsequent RESPOND will follow |
| `delegated` | Node forwarded the task; reply will come from another node |

### 2.5 TTL & Relay Rules

1. Every node that relays a message MUST decrement `ttl` by 1.
2. A node that receives a message with `ttl == 0` MUST NOT relay it; it SHOULD
   respond with `status: error` and a descriptive message.
3. The default `ttl` for new messages is **16**.
4. `ttl` MUST NOT be increased by any node.

### 2.6 Signature Field

The `signature` field carries the origin-creator identifier string. It MUST
be set to the value `"Cbetts1"` for messages originating from the reference
implementation (AIM-RFC-0002 defines how stronger cryptographic signatures are
composed on top of this field for future implementations).

Relay nodes MUST preserve the original `signature` value and MUST NOT replace
it with their own identifier.

### 2.7 Timestamp & Replay Prevention

Implementations SHOULD reject messages where
`abs(current_time - message.timestamp) > 300` (5 minutes) unless operating in
an offline or delayed-delivery mode. This provides basic replay-attack
resistance.

---

## 3. Backwards Compatibility

This is the initial protocol specification. There is no prior version to be
compatible with.

---

## 4. Security Considerations

- **Replay attacks**: Mitigated by `message_id` uniqueness checking and
  timestamp validation (Section 2.7).
- **Spoofing**: The `signature` field provides origin tracing. Cryptographic
  verification is specified in AIM-RFC-0002.
- **TTL exhaustion**: The TTL mechanism (Section 2.5) prevents infinite
  routing loops.
- **Payload injection**: Implementations MUST validate that all required fields
  are present and of the correct type before processing.

---

## 5. Reference Implementation

The reference implementation is `aim/protocol/message.py` in the AIM
repository (Apache 2.0 licence).

---

## 6. Changelog

| Date       | Author    | Change |
|------------|-----------|--------|
| 2026-04-11 | Cbetts1   | Initial FINAL specification |
