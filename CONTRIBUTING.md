# Contributing to AIM — Artificial Intelligence Mesh

Thank you for your interest in contributing.  This document describes the
conventions, branch strategy, and design rules that keep the AIM codebase
coherent and trustworthy.

---

## Table of Contents

1. [Code Style](#code-style)
2. [Branch Rules](#branch-rules)
3. [CreatorSignature Requirement](#creatorsignature-requirement)
4. [Testing](#testing)
5. [Security & Compliance](#security--compliance)
6. [Licence](#licence)

---

## Code Style

- **Python 3.10+** — use `from __future__ import annotations` in every module.
- Follow [PEP 8](https://peps.python.org/pep-0008/) for naming and layout.
- Use `dataclasses` and `Enum` over raw dicts/strings for protocol types.
- Type-annotate every function signature; return types must be explicit.
- Docstrings use the NumPy/Google hybrid style already present in the codebase.
- No external runtime dependencies unless they are optional and gated behind
  `importlib.util.find_spec`.

---

## Branch Rules

| Branch | Purpose |
|---|---|
| `main` | Stable, release-ready code only |
| `dev` | Integration branch; PRs merge here first |
| `feature/<name>` | New features; branch from `dev` |
| `fix/<name>` | Bug fixes; branch from `dev` |
| `release/<version>` | Release preparation; branch from `dev`, merges to `main` |

- All PRs require at least one review before merge.
- CI must be green (all tests pass) before merge.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`.

---

## CreatorSignature Requirement

> **Every public API surface in AIM must carry and propagate the
> `CreatorSignature`.**

This is an architectural rule, not a suggestion.

- Any new `AIMMessage` factory method must include the `signature` field.
- Any new node type must inherit from `BaseNode` (which sets `self.creator`).
- Any new ledger event must pass `signature=` when calling `ledger.record()`.
- The origin creator string (`"Cbetts1"`) must never be altered or removed.

The identity layer is the audit backbone of the mesh.  Omitting signatures
makes traffic untraceable and breaks the design contract.

---

## Testing

```bash
# Install in editable mode (once)
pip install -e .
pip install pytest pytest-asyncio

# Run all tests
python -m pytest tests/ -v
```

- Tests live in `tests/`; one file per layer (`test_protocol.py`,
  `test_node.py`, `test_compute.py`, `test_identity.py`, `test_web.py`).
- Use `asyncio_mode = "auto"` (already set in `pyproject.toml`); mark async
  test methods with `async def test_...`.
- Every new public function needs at least one unit test.
- Do not remove or weaken existing tests.

---

## Security & Compliance

The web gateway (`aim/web/`) must comply with:

- **W3C HTML5** — valid `<!DOCTYPE html>`, proper `lang` attribute, all tags
  closed.
- **WCAG 2.1 AA** — `alt` on images, `aria-label` on interactive controls,
  minimum 4.5:1 colour contrast ratio.
- **GDPR / ePrivacy** — no third-party analytics or tracking scripts; no
  cookies without explicit consent.
- **HTTP Security Headers** — every response from the gateway must include:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Content-Security-Policy: default-src 'self'`
  - `Referrer-Policy: no-referrer`
- **HTTPS** — plain HTTP is acceptable for localhost development only; all
  public deployments must terminate TLS at the reverse proxy (Caddy / nginx).

---

## Licence

AIM is released under the [MIT Licence](LICENSE).  All contributions must be
compatible with this licence.  By submitting a pull request you agree that
your contribution will be licensed under MIT.

Copyright © Cbetts1
