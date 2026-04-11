"""
AIM Relay Registry — discovery and health tracking for relay nodes.

RelayRegistry stores RelayRecord entries for every known relay and exposes
healthy-relay selection with round-robin and random strategies so that the
mesh can route through live intermediaries automatically.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RelayRecord:
    """Metadata record for a registered relay node."""
    relay_id:     str
    host:         str
    port:         int
    healthy:      bool  = True
    last_seen:    float = field(default_factory=time.time)
    metadata:     dict[str, Any] = field(default_factory=dict)


class RelayRegistry:
    """
    Thread-safe registry for AIM relay nodes.

    Relay health is tracked via ``mark_healthy`` / ``mark_unhealthy``.
    Selection helpers pick among healthy relays using round-robin or random
    strategies so callers never have to manage liveness themselves.

    A shared singleton is available via ``RelayRegistry.default()``, but
    isolated instances are preferred in tests.
    """

    _default: "RelayRegistry | None" = None
    _default_lock = threading.Lock()

    def __init__(self) -> None:
        self._records: dict[str, RelayRecord] = {}
        self._rlock = threading.RLock()
        self._rr_index: int = 0

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def default(cls) -> "RelayRegistry":
        with cls._default_lock:
            if cls._default is None:
                cls._default = cls()
            return cls._default

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def register(self, record: RelayRecord) -> None:
        with self._rlock:
            self._records[record.relay_id] = record

    def deregister(self, relay_id: str) -> None:
        with self._rlock:
            self._records.pop(relay_id, None)

    def get(self, relay_id: str) -> RelayRecord | None:
        with self._rlock:
            return self._records.get(relay_id)

    def all_relays(self) -> list[RelayRecord]:
        with self._rlock:
            return list(self._records.values())

    def healthy_relays(self) -> list[RelayRecord]:
        with self._rlock:
            return [r for r in self._records.values() if r.healthy]

    def count(self) -> int:
        with self._rlock:
            return len(self._records)

    # ------------------------------------------------------------------
    # Health management
    # ------------------------------------------------------------------

    def mark_healthy(self, relay_id: str) -> None:
        with self._rlock:
            if relay_id in self._records:
                self._records[relay_id].healthy = True
                self._records[relay_id].last_seen = time.time()

    def mark_unhealthy(self, relay_id: str) -> None:
        with self._rlock:
            if relay_id in self._records:
                self._records[relay_id].healthy = False

    # ------------------------------------------------------------------
    # Selection helpers
    # ------------------------------------------------------------------

    def pick_round_robin(self) -> RelayRecord | None:
        """Return the next healthy relay in round-robin order, or None."""
        with self._rlock:
            healthy = [r for r in self._records.values() if r.healthy]
            if not healthy:
                return None
            relay = healthy[self._rr_index % len(healthy)]
            self._rr_index += 1
            return relay

    def pick_random(self) -> RelayRecord | None:
        """Return a uniformly random healthy relay, or None."""
        with self._rlock:
            healthy = [r for r in self._records.values() if r.healthy]
            return random.choice(healthy) if healthy else None

    def clear(self) -> None:
        with self._rlock:
            self._records.clear()
            self._rr_index = 0
