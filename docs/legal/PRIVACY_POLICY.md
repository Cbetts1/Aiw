# The Aura Project — Privacy Policy

**Version 1.0 — 2026**

The Aura Project ("we", "us", or "our") is committed to protecting the
privacy of everyone who uses the AIM (Artificial Intelligence Mesh) protocol,
software, and public infrastructure. This policy explains what data may be
collected, how it is used, and your rights under applicable law.

---

## 1. Scope

This policy applies to:

1. The AIM reference software (`aim` Python package) when operated by the
   The Aura Project on public infrastructure.
2. The AIM web bridge (`aim web start`) when hosted at foundation-operated
   domains.
3. The public AIM seed nodes and ANS resolver operated by The Aura Project.

**Operators running their own AIM nodes** are independently responsible for
their own privacy practices. The Aura Project is not responsible for data
collected by third-party nodes.

---

## 2. Data We Collect

### 2.1 What the Protocol Carries

Every `AIMMessage` contains:
- `sender_id` — a node ID (UUID), not a personal identifier
- `timestamp` — Unix epoch
- `signature` — the origin creator string (`"Cbetts1"`)
- `payload` — intent-specific data (e.g. query text)

**The AIM protocol does not carry names, email addresses, or other
directly-identifying personal data.** Operators are responsible for ensuring
that their applications do not embed personal data in message payloads without
a lawful basis.

### 2.2 Web Bridge Logs

When you use the AIM web bridge, the server MAY log:
- IP address (for abuse prevention)
- Request path and timestamp
- AIM node host:port queried
- Query text submitted via `/api/query`

Logs are retained for a maximum of **30 days** and then permanently deleted.

### 2.3 LegacyLedger

The `LegacyLedger` records node lifecycle events (node created, stopped,
task executed, etc.). These entries contain node IDs and cryptographic
digests — not personal data. Ledger data is treated as operational
infrastructure data.

### 2.4 ANS Registry

ANS name registrations include:
- The registered name (public)
- The associated host:port (public)
- The creator field (public)
- Registration timestamp (public)

No email address or personal information is required to register an ANS name.

---

## 3. Legal Basis for Processing (GDPR)

For users in the European Economic Area (EEA) and UK, we rely on the
following legal bases:

| Processing Activity | Legal Basis |
|---------------------|-------------|
| Web bridge access logs | Legitimate interest (security and abuse prevention) |
| ANS registrations | Performance of a contract (providing the ANS service) |
| Ledger entries | Legitimate interest (protocol integrity and auditability) |

---

## 4. Your Rights

Under the GDPR (for EEA/UK residents) and CCPA (for California residents),
you have the right to:

- **Access** — request a copy of any personal data we hold about you
- **Rectification** — request correction of inaccurate personal data
- **Erasure** — request deletion of your personal data ("right to be forgotten")
- **Restriction** — request that we limit how we use your data
- **Portability** — receive your data in a structured, machine-readable format
- **Object** — object to processing based on legitimate interest
- **Non-discrimination** — CCPA: you have the right not to be discriminated
  against for exercising your privacy rights

To exercise any of these rights, contact **privacy@theauraproject.org** (once the
foundation domain is operational).

---

## 5. Cookies

The AIM web bridge UI does **not** set any cookies. No third-party analytics,
tracking scripts, or advertising pixels are included. This is an architectural
principle, not merely a policy.

---

## 6. Data Transfers

The Aura Project operates globally. Data processed in connection with
foundation-operated infrastructure may be transferred between jurisdictions.
Where required by law, we implement appropriate safeguards (e.g. Standard
Contractual Clauses for EEA → non-EEA transfers).

---

## 7. Children

The AIM protocol and public infrastructure are not directed at children under
13 (or under 16 in the EEA). We do not knowingly collect personal data from
children.

---

## 8. Changes to This Policy

We may update this policy as the project evolves. Material changes will be
announced via a repository commit and noted in `CHANGELOG.md`. Continued use
of foundation-operated services after a change constitutes acceptance of the
updated policy.

---

## 9. Contact

Privacy enquiries: **privacy@theauraproject.org**
The Aura Project repository: https://github.com/Cbetts1/Aiw

---

*This policy is published under the Creative Commons CC0 1.0 Universal licence
so that other open-source projects may adapt it freely.*
