"""
AIM Legacy Ledger — an append-only log of every significant event in
the mesh, ensuring the origin creator's trace can never be removed.

In production this can be backed by an immutable store (IPFS, blockchain,
or a write-once object-storage bucket).  Here we use an in-process list
with optional JSON-file persistence so the prototype can run anywhere.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

from .signature import CreatorSignature, ORIGIN_CREATOR, AIM_MESH_NAME


class EventKind(str, Enum):
    NODE_CREATED  = "node_created"
    NODE_STOPPED  = "node_stopped"
    TASK_EXECUTED = "task_executed"
    MESSAGE_ROUTED = "message_routed"
    PEER_CONNECTED = "peer_connected"
    MEMORY_SHARED  = "memory_shared"
    CUSTOM         = "custom"
    # Mesh subsystem events
    GATEWAY_CONNECTED    = "gateway_connected"
    GATEWAY_DISCONNECTED = "gateway_disconnected"
    RELAY_PEER_CONNECTED = "relay_peer_connected"
    RELAY_MSG_FORWARDED  = "relay_message_forwarded"
    CONTENT_POSTED       = "content_posted"
    CONTENT_DELETED      = "content_deleted"
    MESH_NODE_JOINED     = "mesh_node_joined"


@dataclass
class LedgerEntry:
    """A single immutable record in the legacy ledger."""
    event_kind:  str
    node_id:     str
    creator:     str          = ORIGIN_CREATOR
    mesh:        str          = AIM_MESH_NAME
    payload:     dict[str, Any] = field(default_factory=dict)
    entry_id:    str          = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:   float        = field(default_factory=time.time)
    signature_digest: str     = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LegacyLedger:
    """
    Thread-safe append-only event ledger.

    Parameters
    ----------
    persist_path : optional file path for JSON persistence.
                   If given, entries are appended to the file on each write.
    """

    def __init__(self, persist_path: str | None = None) -> None:
        self._entries: list[LedgerEntry] = []
        self._lock = threading.RLock()
        self._persist_path = persist_path
        if persist_path and os.path.exists(persist_path):
            self._load(persist_path)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(
        self,
        event_kind: EventKind | str,
        node_id: str,
        payload: dict[str, Any] | None = None,
        signature: CreatorSignature | None = None,
    ) -> LedgerEntry:
        """Append an entry to the ledger."""
        sig_digest = signature.digest if signature else ""
        entry = LedgerEntry(
            event_kind=event_kind.value if isinstance(event_kind, EventKind) else str(event_kind),
            node_id=node_id,
            payload=payload or {},
            signature_digest=sig_digest,
        )
        with self._lock:
            self._entries.append(entry)
        if self._persist_path:
            self._append_to_file(entry)
        return entry

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def all_entries(self) -> list[LedgerEntry]:
        with self._lock:
            return list(self._entries)

    def entries_for_node(self, node_id: str) -> list[LedgerEntry]:
        with self._lock:
            return [e for e in self._entries if e.node_id == node_id]

    def entries_by_kind(self, kind: EventKind | str) -> list[LedgerEntry]:
        kind_val = kind.value if isinstance(kind, EventKind) else str(kind)
        with self._lock:
            return [e for e in self._entries if e.event_kind == kind_val]

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _append_to_file(self, entry: LedgerEntry) -> None:
        try:
            with open(self._persist_path, "a", encoding="utf-8") as fh:  # type: ignore[arg-type]
                fh.write(json.dumps(entry.to_dict()) + "\n")
        except OSError:
            pass  # best-effort persistence

    def _load(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    self._entries.append(LedgerEntry(**d))
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    def to_json(self) -> str:
        with self._lock:
            return json.dumps([e.to_dict() for e in self._entries], indent=2)


# Module-level default ledger (shared across the process unless overridden)
_default_ledger: LegacyLedger | None = None
_dl_lock = threading.Lock()


def default_ledger() -> LegacyLedger:
    global _default_ledger
    with _dl_lock:
        if _default_ledger is None:
            _default_ledger = LegacyLedger()
        return _default_ledger
