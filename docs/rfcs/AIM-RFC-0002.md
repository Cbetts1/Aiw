# AIM-RFC-0002 — Node Identity & Creator Signature

| Field       | Value                                     |
|-------------|-------------------------------------------|
| Number      | AIM-RFC-0002                              |
| Title       | Node Identity, Creator Signature & PKI    |
| Author(s)   | Cbetts1 (The Aura Project)                  |
| Status      | FINAL                                     |
| Created     | 2026-04-11                                |
| Updated     | 2026-04-11                                |
| Supersedes  | —                                         |
| Superseded  | —                                         |

---

## Abstract

This document specifies how AIM nodes establish and prove their identity.
It defines the `CreatorSignature` structure (HMAC-SHA256 origin proof used
in the reference implementation) and the optional PKI layer (Ed25519 key
pairs) that enables open, verifiable node identity on the public mesh.

---

## 1. Motivation

Every node, message, and event in the AIM mesh carries a traceable identity.
This serves two purposes:

1. **Auditability** — the `LegacyLedger` provides an append-only audit trail
   that can prove the provenance of any event.
2. **Trust** — nodes can verify that a peer was created by a known origin and
   has not been tampered with.

The current HMAC-SHA256 `CreatorSignature` provides tamper-detection within a
trust domain where the HMAC key is known. For the public mesh, where nodes
are operated by independent parties, a public-key infrastructure is needed so
that any node can verify any other node's identity without a shared secret.

---

## 2. Specification

### 2.1 Node Identifier

Every AIM node MUST be assigned a **node_id** at creation time. The node_id:

- MUST be a UUID v4 string (128 random bits).
- MUST be globally unique.
- MUST be preserved in the `LegacyLedger` upon creation.
- MUST NOT be reassigned or reused.

### 2.2 Creator Signature (HMAC-SHA256)

The `CreatorSignature` structure binds a node to its origin creator.

#### Fields

| Field        | Type   | Description |
|--------------|--------|-------------|
| `creator`    | string | Origin creator identifier (MUST be `"Cbetts1"` for canonical nodes) |
| `mesh`       | string | Mesh name (MUST be `"AIM"`) |
| `epoch`      | string | Symbolic origin epoch (`"1991"`) |
| `node_id`    | string | UUID v4 (matches the node's node_id) |
| `issued_at`  | float  | Unix epoch seconds when signature was issued |
| `digest`     | string | 64-character lowercase hex HMAC-SHA256 digest |

#### Digest Computation

```
key     = UTF-8("Cbetts1/AIM")
message = UTF-8("{creator}:{mesh}:{epoch}:{node_id}:{issued_at}")
digest  = HMAC-SHA256(key, message).hexdigest()
```

#### Verification

A `CreatorSignature` is valid if and only if recomputing the digest using the
declared fields produces the same value (constant-time comparison MUST be
used to prevent timing attacks).

### 2.3 PKI Layer — Ed25519 Node Key Pairs (Optional)

For the public mesh, implementations MAY generate an Ed25519 key pair per
node. This enables:

- **Open verification** — any node can verify a peer's signature without a
  shared secret.
- **Non-repudiation** — signed messages can be attributed to a specific node
  key with mathematical certainty.

#### Key Generation

An implementation that supports the PKI layer MUST:

1. Generate a fresh Ed25519 key pair (`private_key`, `public_key`) at node
   creation time.
2. Store the `private_key` securely and never transmit it.
3. Include the `public_key` (encoded as URL-safe base64) in `ANNOUNCE`
   messages and `NodeRecord` metadata.

#### Message Signing

When signing a message:

```
signature_bytes = Ed25519.sign(
    private_key,
    UTF-8(message.message_id + ":" + str(message.timestamp))
)
sig_b64 = base64url(signature_bytes)
```

The `sig_b64` value SHOULD be included as `context["node_sig"]` in the
`AIMMessage`.

#### Message Verification

```
valid = Ed25519.verify(
    peer_public_key,
    UTF-8(message.message_id + ":" + str(message.timestamp)),
    base64url_decode(message.context["node_sig"])
)
```

### 2.4 LegacyLedger Integration

Every significant node lifecycle event MUST be recorded in the `LegacyLedger`:

| EventKind        | When to record |
|------------------|----------------|
| `node_created`   | Immediately after node is created |
| `node_stopped`   | When node shuts down gracefully |
| `task_executed`  | After each task completes |
| `message_routed` | When a message is relayed |
| `peer_connected` | When a new peer announces itself |
| `memory_shared`  | When a `MEMORY_SET` is processed |

All ledger entries MUST carry the `signature_digest` of the `CreatorSignature`
active at the time of the event.

### 2.5 Node Record

A `NodeRecord` broadcast in `ANNOUNCE` messages MUST contain:

| Field          | Type         | Required | Description |
|----------------|--------------|----------|-------------|
| `node_id`      | string       | MUST     | UUID v4 |
| `host`         | string       | MUST     | IP address or hostname |
| `port`         | integer      | MUST     | TCP port |
| `capabilities` | list[string] | SHOULD   | Registered capability tags |
| `creator`      | string       | MUST     | Origin creator identifier |
| `public_key`   | string       | MAY      | Ed25519 public key, base64url |

---

## 3. Backwards Compatibility

The PKI layer is fully optional and additive. Nodes that do not support
Ed25519 MUST ignore `context["node_sig"]` fields without error. The
HMAC-SHA256 `CreatorSignature` remains normative for all implementations.

---

## 4. Security Considerations

- **Key storage**: Private keys MUST be stored in an OS-level secure store or
  encrypted file; MUST NOT appear in logs or error messages.
- **Key rotation**: Nodes MAY rotate their Ed25519 key pair periodically;
  old public keys SHOULD be retained in the ledger for historical verification.
- **HMAC key exposure**: The HMAC key `"Cbetts1/AIM"` is public by design
  (it provides tamper-detection, not secrecy). For confidentiality, use TLS
  at the transport layer (AIM-RFC-0004).
- **Timing attacks**: All digest comparisons MUST use constant-time comparison
  (`hmac.compare_digest` in Python).

---

## 5. Reference Implementation

- `aim/identity/signature.py` — `CreatorSignature` (HMAC-SHA256)
- `aim/identity/ledger.py` — `LegacyLedger`
- `aim/identity/pki.py` — Ed25519 optional PKI layer

---

## 6. Changelog

| Date       | Author    | Change |
|------------|-----------|--------|
| 2026-04-11 | Cbetts1   | Initial FINAL specification |
