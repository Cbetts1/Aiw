"""
Meshara Name Service — ANSResolver.

The resolver translates an ``meshara://`` URI into a ``NodeRecord`` that can be
used to open a connection.  It checks the local ``ANSRegistry`` first; remote
resolver queries (over the mesh) are planned for a future release.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from meshara.ans.registry import ANSRegistry, ANSRecord, _normalise
from meshara.node.registry import NodeRecord

if TYPE_CHECKING:
    pass


class ANSResolver:
    """
    Resolve ``meshara://`` names to ``NodeRecord`` instances.

    Parameters
    ----------
    registry:
        The ``ANSRegistry`` to consult.  Defaults to the global singleton.

    Examples
    --------
    >>> registry = ANSRegistry()
    >>> registry.register(ANSRecord("weather.public.meshara", "abc", "10.0.0.1", 7700))
    >>> resolver = ANSResolver(registry)
    >>> record = resolver.resolve("meshara://weather.public.meshara")
    >>> record.host
    '10.0.0.1'
    """

    def __init__(self, registry: ANSRegistry | None = None) -> None:
        self._registry = registry or ANSRegistry.default()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, name: str) -> NodeRecord | None:
        """
        Resolve an ANS name to a ``NodeRecord``.

        Parameters
        ----------
        name:
            An ``meshara://`` URI or a bare ANS name (e.g. ``weather.public.meshara``).

        Returns
        -------
        NodeRecord | None
            The ``NodeRecord`` for the resolved node, or ``None`` if the name
            is not found or the cached record has expired.
        """
        ans_record = self._lookup(name)
        if ans_record is None:
            return None
        return self._to_node_record(ans_record)

    def resolve_ans(self, name: str) -> ANSRecord | None:
        """
        Resolve an ANS name to its ``ANSRecord`` (raw, without conversion).

        Returns ``None`` if the name is not found or the entry has expired.
        """
        return self._lookup(name)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _lookup(self, name: str) -> ANSRecord | None:
        record = self._registry.get(name)
        if record is None:
            return None
        # Honour TTL — treat registration time + ttl_seconds as expiry.
        age = time.time() - record.registered_at
        if age > record.ttl_seconds:
            # Stale entry — remove and return None.
            self._registry.deregister(record.name)
            return None
        return record

    @staticmethod
    def _to_node_record(ans: ANSRecord) -> NodeRecord:
        return NodeRecord(
            node_id=ans.node_id,
            host=ans.host,
            port=ans.port,
            capabilities=list(ans.capabilities),
            creator=ans.creator,
            metadata=dict(ans.metadata),
        )
