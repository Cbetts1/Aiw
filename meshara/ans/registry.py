"""
Meshara Name Service — ANSRecord and ANSRegistry.

The ANSRegistry is an in-memory, thread-safe store that maps normalised
`meshara://` names to node addresses.  It mirrors the role DNS plays for the web.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from meshara.identity.signature import ORIGIN_CREATOR


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

def _normalise(name: str) -> str:
    """Return a lower-cased, scheme-stripped ANS name.

    Examples
    --------
    >>> _normalise("meshara://Weather.Public.meshara")
    'weather.public.meshara'
    >>> _normalise("Weather.Public.meshara")
    'weather.public.meshara'
    """
    name = name.strip()
    if name.lower().startswith("meshara://"):
        name = name[6:]
    return name.lower()


def _validate(name: str) -> None:
    """Raise ValueError if *name* is not a valid normalised ANS name."""
    if not name:
        raise ValueError("ANS name must not be empty")
    if len(name) > 253:
        raise ValueError("ANS name must not exceed 253 characters")
    labels = name.split(".")
    if len(labels) < 2:
        raise ValueError("ANS name must contain at least two labels (e.g. 'foo.meshara')")
    for label in labels:
        if not label:
            raise ValueError("ANS name must not contain empty labels (double dots)")
        if len(label) > 63:
            raise ValueError(f"ANS label '{label}' must not exceed 63 characters")
        for ch in label:
            if not (ch.isascii() and (ch.isalnum() or ch == "-")):
                raise ValueError(
                    f"ANS label '{label}' contains invalid character '{ch}'. "
                    "Only ASCII letters, digits, and hyphens are allowed."
                )
        if label.startswith("-") or label.endswith("-"):
            raise ValueError(f"ANS label '{label}' must not start or end with a hyphen")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ANSRecord:
    """An ANS name-to-node mapping.

    Parameters
    ----------
    name:
        Normalised ANS name (e.g. ``weather.public.meshara``).  May be provided
        with or without the ``meshara://`` scheme prefix — it is normalised
        automatically.
    node_id:
        UUID v4 of the target Meshara node.
    host:
        Hostname or IP address of the target node.
    port:
        TCP port of the target node.
    capabilities:
        List of capability tags advertised by the target node.
    creator:
        Origin creator identifier (defaults to ``ORIGIN_CREATOR``).
    registered_at:
        Unix epoch timestamp of registration (auto-set if not provided).
    ttl_seconds:
        Client-side cache TTL in seconds (default 3600).
    metadata:
        Arbitrary additional key-value data.
    """

    name:           str
    node_id:        str
    host:           str
    port:           int
    capabilities:   list[str]        = field(default_factory=list)
    creator:        str              = ORIGIN_CREATOR
    registered_at:  float            = field(default_factory=time.time)
    ttl_seconds:    int              = 3600
    metadata:       dict[str, Any]   = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalised = _normalise(self.name)
        _validate(normalised)
        self.name = normalised
        if not (1 <= self.port <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got {self.port}")

    @property
    def meshara_uri(self) -> str:
        """Return the canonical ``meshara://`` URI for this record."""
        return f"meshara://{self.name}"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ANSRegistry:
    """
    Thread-safe in-memory ANS name registry.

    A single shared instance is available via ``ANSRegistry.default()``.
    Isolated instances can be created for testing.
    """

    _default: "ANSRegistry | None" = None
    _class_lock = threading.Lock()

    def __init__(self) -> None:
        self._records: dict[str, ANSRecord] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Singleton helper
    # ------------------------------------------------------------------

    @classmethod
    def default(cls) -> "ANSRegistry":
        with cls._class_lock:
            if cls._default is None:
                cls._default = cls()
            return cls._default

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def register(self, record: ANSRecord) -> None:
        """Register or update an ANS record."""
        with self._lock:
            self._records[record.name] = record

    def deregister(self, name: str) -> None:
        """Remove an ANS record by name."""
        normalised = _normalise(name)
        with self._lock:
            self._records.pop(normalised, None)

    def get(self, name: str) -> ANSRecord | None:
        """Look up a record by name (with or without ``meshara://`` prefix)."""
        normalised = _normalise(name)
        with self._lock:
            return self._records.get(normalised)

    def all_records(self) -> list[ANSRecord]:
        """Return all registered ANS records."""
        with self._lock:
            return list(self._records.values())

    def find_by_capability(self, capability: str) -> list[ANSRecord]:
        """Return records whose node advertises *capability*."""
        with self._lock:
            return [r for r in self._records.values() if capability in r.capabilities]

    def find_by_creator(self, creator: str) -> list[ANSRecord]:
        """Return records registered by *creator*."""
        with self._lock:
            return [r for r in self._records.values() if r.creator == creator]

    def count(self) -> int:
        with self._lock:
            return len(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
