# AIM Threat Model

**Version 1.0 — 2026**

This document describes the security threat model for the AIM (Artificial
Intelligence Mesh) protocol and reference implementation. It is intended for
security researchers, node operators, and contributors evaluating the security
properties of the system.

---

## 1. Assets

The following assets are considered in-scope for security analysis:

| Asset | Description | Sensitivity |
|-------|-------------|-------------|
| AIM messages in transit | `AIMMessage` payloads travelling between nodes | Medium–High |
| Node identity (`CreatorSignature`) | HMAC digest proving node provenance | High |
| Ed25519 private keys | Node signing keys (if PKI is deployed) | Critical |
| `LegacyLedger` contents | Append-only event audit trail | High |
| `NodeRegistry` state | List of known peers and their capabilities | Medium |
| ANS registrations | Name→address mappings | Medium |
| Web bridge query logs | IP addresses + query text | Medium |
| Node knowledge base | Rules added via `add_rule()` / `EducationBot` | Medium |

---

## 2. Threat Actors

| Actor | Motivation | Capability |
|-------|------------|------------|
| Script kiddie | Curiosity, vandalism | Low: off-the-shelf tools |
| Malicious node operator | Disruption, data harvesting | Medium: can run AIM nodes |
| Nation-state / advanced attacker | Surveillance, protocol disruption | High: traffic analysis, zero-days |
| Rogue insider | Sabotage, theft | Medium: repository/infra access |

---

## 3. Threat Categories & Mitigations

### 3.1 Replay Attacks

**Threat:** An attacker captures a valid `AIMMessage` and retransmits it to
cause duplicate task execution or unauthorised state changes.

**Mitigations:**
- Each message carries a UUID v4 `message_id` (128 random bits). Nodes SHOULD
  maintain a short-lived cache of seen `message_id`s and reject duplicates.
- The `timestamp` field enables time-window validation. Nodes SHOULD reject
  messages where `abs(now - timestamp) > 300` seconds.

**Residual risk:** Nodes that do not implement `message_id` deduplication
remain vulnerable within the timestamp window.

---

### 3.2 Sybil Attacks

**Threat:** An adversary creates a large number of fake nodes to manipulate
task routing, poison the `NodeRegistry`, or dominate ANS registrations.

**Mitigations:**
- `CreatorSignature` ties every node to an origin creator. A mass-Sybil
  operation would require generating many unique HMAC digests, but because
  the HMAC key is public (`Cbetts1/AIM`), this is computationally trivial
  without stronger identity.
- The `ProtectionAgent` (AIM City) monitors registry for anomalous patterns.
- The AIM Foundation's public blacklist names known Sybil clusters.

**Planned improvement:** Ed25519 key pairs (AIM-RFC-0002 §2.3) with a
proof-of-work or social-attestation registration step for public ANS names.

---

### 3.3 Man-in-the-Middle (MitM)

**Threat:** An attacker intercepts and modifies messages between nodes.

**Mitigations:**
- TLS 1.2+ (`aim/transport/tls.py`) encrypts and authenticates the transport
  channel. All public deployments MUST use TLS.
- The `CreatorSignature` and Ed25519 message signatures allow recipients to
  detect message tampering even if TLS is absent.
- HTTP security headers (`X-Content-Type-Options`, `Content-Security-Policy`,
  etc.) protect the web bridge against content injection.

**Residual risk:** Nodes communicating over plain TCP (non-TLS) are vulnerable
to passive interception. This is acceptable only for localhost development.

---

### 3.4 Malicious Nodes

**Threat:** A node operator acts maliciously — returning false query results,
consuming tasks without completing them, or attempting to extract memory from
other nodes.

**Mitigations:**
- The `ProtectionAgent` audits the registry and blacklists nodes with invalid
  signatures.
- The `IntegrityGuard` takes SHA-256 snapshots of critical configuration and
  alerts on divergence.
- The `LegacyLedger` provides an immutable audit trail; every action is
  attributable to a node_id.
- The `TaskRouter` supports `ROUND_ROBIN` and `BROADCAST` strategies that
  reduce reliance on any single node.

---

### 3.5 Denial of Service (DoS)

**Threat:** An attacker floods a node with messages to exhaust its resources.

**Mitigations:**
- The TTL field (maximum 16 hops) limits amplification via relay.
- Nodes SHOULD implement per-IP and per-node-ID rate limiting.
- The web bridge caps request body size at 1 MiB and enforces connection
  timeouts (10 seconds).
- AIM Foundation seed nodes apply network-level rate limiting.

---

### 3.6 Privacy / Data Leakage

**Threat:** Sensitive personal data ends up in `AIMMessage` payloads,
`LegacyLedger` entries, or node knowledge bases.

**Mitigations:**
- The AIM protocol carries no personal data by design; node_ids are UUIDs.
- The [Privacy Policy](legal/PRIVACY_POLICY.md) requires operators to obtain
  lawful basis before embedding personal data in messages.
- The web bridge retains access logs for a maximum of 30 days.
- No third-party analytics or cookies are included in the web UI.

---

### 3.7 Supply-Chain Attacks

**Threat:** A malicious dependency is introduced into the `aim` package.

**Mitigations:**
- AIM has **zero mandatory runtime dependencies**. The attack surface is
  limited to the Python standard library.
- The `cryptography` package (optional, for Ed25519) must be pinned by
  operators and verified against known-good hashes.
- The GitHub repository uses branch protection and required code review.

---

### 3.8 Ledger Tampering

**Threat:** An attacker modifies historical `LegacyLedger` entries to erase
evidence of malicious activity.

**Mitigations:**
- The `LegacyLedger` is append-only in the reference implementation; entries
  cannot be deleted or modified via the public API.
- Each entry carries a `signature_digest` that chains it to its
  `CreatorSignature`.
- The `IntegrityGuard` can detect tampering via SHA-256 snapshots.

**Planned improvement:** IPFS or blockchain anchoring for production ledgers.

---

## 4. Out-of-Scope Threats

The following are explicitly out of scope for the core protocol:

- Physical security of the host machine running an AIM node.
- Operating system or hypervisor vulnerabilities.
- Vulnerabilities in third-party reverse proxies (nginx, Caddy, etc.) used
  to terminate TLS.
- Social engineering attacks against node operators.

---

## 5. Security Contacts

To report a vulnerability, see [SECURITY.md](../SECURITY.md).

---

*AIM Foundation — 2026*
