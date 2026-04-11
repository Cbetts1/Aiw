# AIM Interoperability & Conformance Guide

**Version 1.0 — 2026**

This document describes how to verify that an AIM implementation is conformant
with the AIM protocol specifications and how to test cross-language / cross-
platform interoperability.

---

## 1. Overview

Because AIM is designed to be a universal open standard — like HTTP — it is
essential that independent implementations (Python, Go, Rust, JavaScript, etc.)
can communicate correctly. Conformance testing ensures this.

---

## 2. Conformance Levels

| Level | Description |
|-------|-------------|
| **Level 1 — Message** | Can serialise and deserialise all `AIMMessage` intents correctly |
| **Level 2 — Transport** | Can exchange messages over TCP and TLS |
| **Level 3 — Node** | Can run as a node (accept connections, handle QUERY/HEARTBEAT, reply) |
| **Level 4 — Mesh** | Can discover peers, join a mesh, and route tasks |
| **Level 5 — ANS** | Can register and resolve ANS names |
| **Level 6 — PKI** | Supports Ed25519 identity and message signing |

An implementation claiming "AIM-conformant" MUST pass Levels 1–3. Levels 4–6
are strongly recommended for production nodes.

---

## 3. Running the Conformance Suite

The AIM reference repository includes a conformance test suite in `tests/`.

### Prerequisites

```bash
pip install -e .
pip install pytest pytest-asyncio
```

### Run all tests

```bash
python -m pytest tests/ -v
```

### Level-specific test tags (coming in future releases)

```bash
# Level 1 — message format
python -m pytest tests/test_protocol.py -v

# Level 2 — transport
python -m pytest tests/test_transport.py -v

# Level 3 — node behaviour
python -m pytest tests/test_node.py -v

# Level 4 — mesh routing
python -m pytest tests/test_compute.py -v

# Level 5 — ANS
python -m pytest tests/test_ans.py -v

# Level 6 — PKI
python -m pytest tests/test_pki.py -v
```

---

## 4. Cross-Implementation Testing

To verify that your implementation can talk to the reference implementation:

### Step 1 — Start a reference node

```bash
aim node start --host 127.0.0.1 --port 7700
```

### Step 2 — Send a QUERY from your implementation

Your implementation must construct a valid AIM message envelope (see
AIM-RFC-0001) and send it over TCP with a 4-byte length prefix.

Expected response:

```json
{
  "intent": "respond",
  "payload": { "result": "...", "status": "ok" },
  "signature": "Cbetts1"
}
```

### Step 3 — Send a HEARTBEAT

Expected response:

```json
{
  "intent": "respond",
  "payload": { "result": { "alive": true, "node_id": "..." }, "status": "ok" },
  "signature": "Cbetts1"
}
```

### Step 4 — Announce and be discovered

Send an `ANNOUNCE` message. The reference node will add your implementation to
its registry and reply with its own `ANNOUNCE`.

---

## 5. AIM-over-TLS

AIM-over-TLS wraps the standard TCP+length-prefix transport in TLS 1.2+.
Servers MUST use a valid certificate (self-signed is acceptable for testing).

Helper utilities are provided in `aim/transport/tls.py`:

```python
from aim.transport.tls import create_client_ssl_context, create_server_ssl_context

# Client (no cert verification for testing)
ssl_ctx = create_client_ssl_context(verify=False)
reader, writer = await asyncio.open_connection(host, port, ssl=ssl_ctx)

# Server
ssl_ctx = create_server_ssl_context("server.crt", "server.key")
server = await asyncio.start_server(handler, host, port, ssl=ssl_ctx)
```

---

## 6. AIM-over-WebSocket

The web bridge (`aim/web/server.py`) provides an HTTP gateway that translates
browser HTTP requests into AIM messages. Direct WebSocket support (for
browser↔node connections) is planned in a future RFC.

---

## 7. Test Vector Reference

The following test vectors are provided for Level 1 conformance testing.

### QUERY message

Input:
```json
{
  "intent": "query",
  "payload": { "text": "What is AIM?" },
  "sender_id": "test-node",
  "receiver_id": null,
  "message_id": "00000000-0000-0000-0000-000000000001",
  "correlation_id": null,
  "timestamp": 0.0,
  "context": {},
  "signature": "Cbetts1",
  "ttl": 16
}
```

Expected wire encoding:
1. Serialise to JSON (compact, no extra whitespace required).
2. Prepend a 4-byte big-endian unsigned integer equal to the byte length of
   the JSON string.

Implementations MUST accept any valid JSON (with or without whitespace) and
MUST be able to round-trip all field types correctly.

---

## 8. Reporting Conformance

Once your implementation passes all applicable levels, open a GitHub Discussion
titled `[CONFORMANCE] <Language/Platform> — Levels N–M` to be listed in the
AIM ecosystem directory.
