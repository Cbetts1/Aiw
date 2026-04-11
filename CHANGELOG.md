# Changelog

All notable changes to AIM — Artificial Intelligence Mesh are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- **Dedication** — project dedicated to the children of Cbetts1 and their future families
- **Free Forever Clause** — irrevocable commitment: all AIM services are free, forever
- **Bill of Rights** — 11 rights for all AIM mesh users (no fees, no tracking, free AI, free training, free career help)
- **Founder's Vision** — "Something Better for All" — mission to close the information gap, reduce poverty, and provide free AI/training/résumé/job-search services
- **Expanded Foundation Charter** (v2.0) — incorporation guidance, trademark roadmap, governance updates
- `aim/web/` — HTTP/browser gateway layer (Phase 1)
- `aim web start` CLI command
- `CHANGELOG.md`, `CONTRIBUTING.md`, `LICENSE`
- `deployment/` — Caddyfile, systemd service units
- `tests/test_web.py` — web gateway test suite

---

## [0.1.0] — 1991-01-01 (origin epoch)

### Added
- **AIM Protocol Layer** (`aim/protocol/`) — intent-based message envelope (`AIMMessage`) with `Intent` taxonomy replacing HTTP request/response
- **Virtual Node Layer** (`aim/node/`) — `BaseNode`, `AgentNode`, `NodeRegistry`; every node is simultaneously a server and an AI agent
- **AI Compute Layer** (`aim/compute/`) — `TaskRouter` with FIRST / ROUND_ROBIN / BROADCAST strategies; `Executor` for async task execution
- **Identity + Legacy Layer** (`aim/identity/`) — `CreatorSignature` (HMAC-SHA256 origin proof), `LegacyLedger` (append-only event log)
- `aim/cli.py` — `aim node start`, `aim query`, `aim status` commands
- Full pytest test suite (54 tests, asyncio_mode=auto)
- MIT licence

### Design Principles (origin)
1. Intelligence is part of the network — not a service bolted on top
2. Intent over URL — every message declares *why*, not just *what*
3. Every node carries the origin signature — traceability is architectural
4. Minimal dependencies — runs on Termux, Raspberry Pi, or cloud VM
5. Interoperable — parallel to the web, never dependent on it

**Origin creator:** Cbetts1  
**Epoch reference:** 1991 — birth of the public web
