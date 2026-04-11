# The Aura Project — Abuse Policy

**Version 1.0 — 2026**

The AIM (Artificial Intelligence Mesh) is built to be universally accessible
and free for all of humanity — the same ethos that guided the World Wide Web.
To protect that openness, The Aura Project maintains this Abuse Policy.

---

## 1. Prohibited Uses

The AIM protocol, public infrastructure, and software MUST NOT be used to:

1. **Spam or bulk unsolicited messaging** — sending QUERY or TASK messages in
   bulk to nodes without the operator's consent.
2. **Denial-of-service attacks** — flooding nodes with heartbeats, messages,
   or connection attempts to degrade availability.
3. **Signature forgery** — attempting to spoof another node's
   `CreatorSignature` or Ed25519 key pair.
4. **Malware distribution** — transmitting executable code or payloads
   designed to compromise receiving nodes.
5. **Illegal content** — transmitting or storing content that is illegal in
   the jurisdiction of the operator or recipient, including but not limited to
   CSAM, terrorism-related content, and content that violates export controls.
6. **Privacy violations** — transmitting personal data without a lawful basis
   under applicable law (GDPR, CCPA, etc.).
7. **Sybil attacks** — operating large numbers of fake nodes to manipulate
   routing or the ANS registry.
8. **Ledger tampering** — attempting to modify or delete entries from the
   `LegacyLedger`.

---

## 2. Reporting Abuse

To report abuse of The Aura Project infrastructure:

- **Email**: abuse@theauraproject.org (once the foundation domain is operational)
- **GitHub issue**: Open an issue titled `[ABUSE REPORT] Brief description`
  in the repository

Include:
- The source `node_id` or IP address if known
- A description of the abusive behaviour
- Timestamps and any supporting evidence (log excerpts, message IDs)

We aim to acknowledge reports within **48 hours** and take action within
**7 days** for confirmed violations.

---

## 3. Enforcement

The `ProtectionAgent` (part of AIM City governance) provides automated
enforcement at the protocol level:

- Nodes with invalid `CreatorSignature` values are **automatically blacklisted**
  from the city registry.
- Nodes that exceed configurable rate limits may be temporarily suspended.
- The `IntegrityGuard` monitors ledger entries for tampering and alerts
  operators immediately upon detection.

Foundation-operated seed nodes and ANS resolvers may apply additional
network-level blocks for persistent abusers.

---

## 4. Blacklisting

A node may be added to the **Aura Project Blacklist** if it is found to be
engaged in any prohibited use listed in Section 1.

Blacklist entries are:
- Published in The Aura Project's public blacklist feed.
- Signed by the Foundation's Ed25519 key so that automated enforcement is
  possible.
- Subject to appeal (see Section 5).

Operators of AIM infrastructure are encouraged (but not required) to subscribe
to the public blacklist.

---

## 5. Appeals

Any node operator who believes their node has been incorrectly blacklisted may
appeal by:

1. Opening a GitHub issue titled `[BLACKLIST APPEAL] node_id: <your_node_id>`.
2. Providing evidence that the flagged activity was a false positive or has
   been remediated.

Appeals are reviewed by at least two The Aura Project stewards within **14 days**.
Decisions may be appealed once more to the full Foundation board.

---

## 6. Good-Faith Research

Security researchers acting in good faith to improve AIM are exempt from this
policy provided they:

- Report findings to **security@theauraproject.org** before public disclosure.
- Do not disrupt real users or operators.
- Follow the responsible disclosure process in [SECURITY.md](../../SECURITY.md).

---

## 7. Jurisdiction-Neutral Design

The AIM protocol itself is jurisdiction-neutral. This policy applies only to
foundation-operated infrastructure. Independent operators are responsible for
their own compliance with applicable laws.

---

*The Aura Project — keeping the mesh open for everyone.*
