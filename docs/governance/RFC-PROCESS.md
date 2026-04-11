# AIM RFC Process

**Version 1.0 — 2026**

The AIM RFC (Request for Comment) process is modelled on the IETF RFC system.
It provides a transparent, community-driven mechanism for evolving the AIM
protocol in a way that is open to everyone.

---

## Scope

An RFC is required for any change that affects:

- The `AIMMessage` envelope format or serialisation
- The `Intent` taxonomy (adding, renaming, or deprecating an intent type)
- The `CreatorSignature` / PKI identity system
- The `NodeRegistry` peer-discovery mechanism
- The `ANS` (AIM Name Service) name resolution protocol
- Transport-layer bindings (TCP, TLS, WebSocket, …)
- The `LegacyLedger` event format
- Any wire-format change that would break cross-implementation compatibility

The following **do not** require an RFC:

- Bug fixes that do not change the wire format
- Documentation corrections
- Test additions or refactoring
- Internal implementation changes with identical externally-observable behaviour

---

## RFC States

```
DRAFT → LAST_CALL → ACCEPTED → FINAL
                  ↘ REJECTED
                  ↘ WITHDRAWN
```

| State | Meaning |
|-------|---------|
| `DRAFT` | Open for community discussion; not stable |
| `LAST_CALL` | 14-day final comment period; maintainers signal readiness to decide |
| `ACCEPTED` | Approved by the AIM Foundation stewards; implementation may begin |
| `FINAL` | Reference implementation merged; spec is normative |
| `REJECTED` | Not accepted; reasons documented in the RFC |
| `WITHDRAWN` | Author withdrew the proposal |

---

## Step-by-Step Process

### Step 1 — Pre-RFC Discussion

Before writing a full RFC, open a **GitHub Discussion** in the
`Protocol Proposals` category with the title `[RFC] Your Proposal Title`.

Use this to gather early feedback and check whether the idea has community
support. There is no minimum duration for this step.

### Step 2 — Write the Draft RFC

Clone the repository and create a new file in `docs/rfcs/` following the
naming convention:

```
docs/rfcs/AIM-RFC-NNNN.md
```

where `NNNN` is the next available four-digit number (zero-padded).

Use the template below as your starting point.

### Step 3 — Open a Pull Request

Open a pull request with the new RFC document. Title it:

```
docs(rfc): AIM-RFC-NNNN — Your Title Here
```

The PR description must link to the original GitHub Discussion.

### Step 4 — Community Review (DRAFT)

The RFC stays in `DRAFT` state during review. Anyone may comment. The author
is expected to respond to all substantive comments and update the document
accordingly.

### Step 5 — Last Call

When the author and at least two maintainers agree that the RFC is ready, a
maintainer changes the status to `LAST_CALL` and announces a 14-day final
comment period on the mailing list and in the GitHub Discussion.

### Step 6 — Decision

After the `LAST_CALL` period, the AIM Foundation stewards make a final
decision: `ACCEPTED`, `REJECTED`, or extend the review with a new `LAST_CALL`.

### Step 7 — Implementation & Finalisation

Once `ACCEPTED`, contributors may implement the RFC in the reference codebase.
When the implementation is merged into `main` and passes CI, the RFC is marked
`FINAL`.

---

## RFC Template

```markdown
# AIM-RFC-NNNN — Title

| Field       | Value                    |
|-------------|--------------------------|
| Number      | AIM-RFC-NNNN             |
| Title       | Your RFC Title           |
| Author(s)   | Your Name <email>        |
| Status      | DRAFT                    |
| Created     | YYYY-MM-DD               |
| Updated     | YYYY-MM-DD               |
| Supersedes  | —                        |
| Superseded  | —                        |

## Abstract

One paragraph summary of what this RFC proposes and why.

## Motivation

Why is this change needed? What problem does it solve?

## Specification

Normative description of the proposed change. Use "MUST", "SHOULD", "MAY"
(RFC 2119 keywords) for normative requirements.

## Backwards Compatibility

Does this change break existing implementations? If so, describe the migration
path.

## Security Considerations

Are there any security implications? Reference the threat model if relevant.

## Reference Implementation

Link to the PR or branch that implements this RFC (if available).

## Open Questions

List unresolved questions that community review should address.

## Changelog

| Date | Author | Change |
|------|--------|--------|
| YYYY-MM-DD | Name | Initial draft |
```

---

## Normative Keywords

This document uses the following normative keywords as defined by
[RFC 2119](https://www.ietf.org/rfc/rfc2119.txt):

- **MUST** / **REQUIRED** / **SHALL** — absolute requirement
- **MUST NOT** / **SHALL NOT** — absolute prohibition
- **SHOULD** / **RECOMMENDED** — strong recommendation; valid reasons to deviate exist
- **SHOULD NOT** / **NOT RECOMMENDED** — strong discouragement; valid reasons to deviate exist
- **MAY** / **OPTIONAL** — truly optional

---

## Governance & Appeals

Decisions made by AIM Foundation stewards may be appealed by opening a new
GitHub Discussion with the title `[APPEAL] AIM-RFC-NNNN`. The appeal is
reviewed by a panel of at least three stewards who were not involved in the
original decision.

The long-term goal is to transition governance to a community-elected Standards
Body with no single controlling entity, following the same path taken by the
IETF and W3C.

---

*AIM Foundation — open governance for a universal AI-native internet layer.*
