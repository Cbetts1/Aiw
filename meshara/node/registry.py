"""
Meshara Node Registry — in-process discovery and lookup of virtual nodes.

For a distributed deployment, this module can be swapped for a DHT or
gossip-protocol based registry without changing any of the node code.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NodeRecord:
    """Metadata record for a registered node."""
    node_id:      str
    host:         str
    port:         int
    capabilities: list[str] = field(default_factory=list)
    creator:      str = "Cbetts1"
    metadata:     dict[str, Any] = field(default_factory=dict)


class NodeRegistry:
    """
    Thread-safe in-process registry for Meshara nodes.

    A single shared instance is used by default (``NodeRegistry.default()``),
    but you can create isolated registries for testing.
    """

    _default: "NodeRegistry | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._records: dict[str, NodeRecord] = {}
        self._rlock = threading.RLock()

    # ------------------------------------------------------------------
    # Singleton helper
    # ------------------------------------------------------------------

    @classmethod
    def default(cls) -> "NodeRegistry":
        with cls._lock:
            if cls._default is None:
                cls._default = cls()
            return cls._default

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def register(self, record: NodeRecord) -> None:
        with self._rlock:
            self._records[record.node_id] = record

    def deregister(self, node_id: str) -> None:
        with self._rlock:
            self._records.pop(node_id, None)

    def get(self, node_id: str) -> NodeRecord | None:
        with self._rlock:
            return self._records.get(node_id)

    def all_nodes(self) -> list[NodeRecord]:
        with self._rlock:
            return list(self._records.values())

    def find_by_capability(self, capability: str) -> list[NodeRecord]:
        with self._rlock:
            return [r for r in self._records.values() if capability in r.capabilities]

    def count(self) -> int:
        with self._rlock:
            return len(self._records)

    def clear(self) -> None:
        with self._rlock:
            self._records.clear()
