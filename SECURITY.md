# Security Policy — AIM (Artificial Intelligence Mesh)

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅ Yes    |

Only the latest release on the `main` branch receives security fixes.

---

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

Report vulnerabilities privately using one of the following channels:

1. **GitHub Private Security Advisory** — click *"Report a vulnerability"* on
   the [Security tab](../../security/advisories/new) of this repository.
2. **Email** — send details to **security@aim-mesh.org** (once the foundation
   domain is operational). Encrypt with the AIM Foundation PGP key if available.

### What to Include

* Description of the vulnerability and its potential impact
* Steps to reproduce (proof-of-concept code is welcome)
* Affected version(s)
* Any suggested remediation you may have

### Response Timeline

| Step | Target |
|------|--------|
| Acknowledgement | Within 48 hours |
| Initial assessment | Within 7 days |
| Fix or mitigation | Within 30 days for critical; 90 days for others |
| Public disclosure | Coordinated with the reporter after fix is released |

We follow responsible disclosure. We will credit you in the release notes
unless you request anonymity.

---

## Bug Bounty Programme

AIM operates a **community bug bounty** programme. Critical vulnerabilities
that are responsibly disclosed and verified may receive recognition in the
AIM Hall of Fame (published in `SECURITY_HALL_OF_FAME.md`) and a mention in
the release notes.

A formal monetary bounty programme via HackerOne or equivalent will be
announced once the AIM Foundation is formally incorporated.

### Severity Classification

| Severity | Examples |
|----------|---------|
| **Critical** | Remote code execution, private key extraction, full node compromise |
| **High** | Signature forgery, HMAC bypass, denial of service on seed nodes |
| **Medium** | Information disclosure, partial authentication bypass |
| **Low** | Configuration issues, non-exploitable edge cases |

---

## Threat Model Summary

The full threat model is documented in [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).
Key categories covered:

1. **Replay attacks** — mitigated by `message_id` (UUID) + `timestamp` fields on
   every `AIMMessage`; nodes should reject messages older than a configurable
   window.
2. **Sybil attacks** — mitigated by `CreatorSignature` (HMAC-SHA256) chained to
   the origin creator; the future PKI layer (Ed25519) strengthens this further.
3. **Man-in-the-middle** — mitigated by TLS transport (`aim/transport/tls.py`);
   all public deployments MUST terminate TLS.
4. **Malicious nodes** — mitigated by `ProtectionAgent` + `IntegrityGuard` in
   `aim/city/`; the `LegacyLedger` provides an append-only audit trail.
5. **Privacy / data leakage** — nodes MUST NOT store personal data without
   explicit operator consent; see [`docs/legal/PRIVACY_POLICY.md`](docs/legal/PRIVACY_POLICY.md).
6. **Supply-chain attacks** — AIM has zero mandatory runtime dependencies;
   optional dependencies (`cryptography`) should be pinned by operators.

---

## Cryptographic Primitives in Use

| Primitive | Used For | Notes |
|-----------|---------|-------|
| HMAC-SHA256 | `CreatorSignature` digest | Stdlib `hmac` + `hashlib`; no external deps |
| Ed25519 (optional) | Node PKI key-pairs | `aim/identity/pki.py`; requires `cryptography` package |
| SHA-256 | `IntegrityGuard` checksums | Stdlib `hashlib` |
| TLS 1.2+ | Transport encryption | Stdlib `ssl`; operators must supply certificates |

**Export Control Note:** HMAC-SHA256 and SHA-256 are classified under ECCN EAR99
(no export licence required for most jurisdictions). Ed25519, when added, falls
under the same classification. Operators in restricted jurisdictions are
responsible for their own compliance.

---

*Last updated: 2026 — AIM Foundation*
*Free, open-source, and dedicated to the public forever.*
