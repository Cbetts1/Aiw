# AIM Intent Registry

**Maintainer:** The Aura Project Protocol Working Group  
**Version:** 1.0 — 2026

This registry lists all **official AIM Intent types** that conformant
implementations must support. New intents must be registered via the RFC
process (see [docs/governance/RFC-PROCESS.md](../governance/RFC-PROCESS.md)).

---

## Registered Intents

| Intent        | RFC          | Status    | Direction | Description |
|---------------|--------------|-----------|-----------|-------------|
| `query`       | AIM-RFC-0001 | PERMANENT | →         | Request information or a reasoning response |
| `task`        | AIM-RFC-0001 | PERMANENT | →         | Delegate an executable unit of work |
| `delegate`    | AIM-RFC-0001 | PERMANENT | →         | Forward a task to another node |
| `respond`     | AIM-RFC-0001 | PERMANENT | ←         | Reply to a prior message |
| `announce`    | AIM-RFC-0001 | PERMANENT | →/←       | Broadcast node presence and capabilities |
| `heartbeat`   | AIM-RFC-0001 | PERMANENT | →/←       | Liveness probe |
| `memory_set`  | AIM-RFC-0001 | PERMANENT | →         | Write a key-value pair to shared mesh memory |
| `memory_get`  | AIM-RFC-0001 | PERMANENT | →         | Read a key-value pair from shared mesh memory |
| `spawn`       | AIM-RFC-0001 | PERMANENT | →         | Request creation of a child node |

---

## Intent Status Definitions

| Status      | Meaning |
|-------------|---------|
| `PERMANENT` | Core intent; will never be removed from the specification |
| `STABLE`    | Standardised and in wide use; may only be changed by new RFC |
| `PROVISIONAL` | Accepted by RFC but not yet widely deployed |
| `EXPERIMENTAL` | In community review; not yet accepted |
| `DEPRECATED` | Retained for backwards compatibility; new code SHOULD NOT use |
| `HISTORIC` | Removed from the specification; retained for reference |

---

## Requesting a New Intent

1. Read [AIM-RFC-0001](../rfcs/AIM-RFC-0001.md) to understand the intent model.
2. Open a GitHub Discussion titled `[RFC] New Intent: <your_intent_name>`.
3. Follow the [RFC process](../governance/RFC-PROCESS.md) to completion.
4. Upon RFC acceptance, the intent will be added to this registry.

### Naming Rules

- Intent names MUST be lowercase ASCII.
- Intent names MUST NOT contain spaces; use underscores (`memory_set`).
- Intent names MUST be globally unique in this registry.
- Intent names SHOULD be self-describing verbs or verb phrases.
- Vendor-specific or experimental intents SHOULD use a namespace prefix
  separated by a colon (e.g. `mycompany:custom_intent`). Prefixed intents do
  not require RFC registration but MUST NOT conflict with registered names.

---

## Extension Intents (Vendor/Community)

The following table tracks community-registered extension intents. These are
not part of the core specification and do not require The Aura Project approval.

| Intent (prefixed)       | Registrant     | Description |
|-------------------------|----------------|-------------|
| *(none registered yet)* | —              | — |

To add an entry, open a PR updating this table. No RFC is required for
vendor-prefixed intents.
