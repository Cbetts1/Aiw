"""
AIM Health — Reporter and snapshot types.

``HealthReporter`` provides a structured view of a node's current health,
suitable for both human inspection and programmatic consumption via HTTP.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from aim.health.metrics import SystemMetrics


@dataclass
class HealthSnapshot:
    """
    Point-in-time health reading for an AIM node.

    Parameters
    ----------
    node_id    : UUID string of the reporting node.
    timestamp  : Unix timestamp when the snapshot was taken.
    status     : ``"healthy"``, ``"degraded"``, or ``"unhealthy"``.
    uptime     : Seconds since the node started.
    peer_count : Number of currently connected peers.
    task_count : Number of in-flight tasks.
    system     : Low-level system metrics.
    errors     : Active error messages at the time of the snapshot.
    """

    node_id: str
    timestamp: float
    status: str
    uptime: float
    peer_count: int
    task_count: int
    system: SystemMetrics
    errors: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping."""
        return {
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "status": self.status,
            "uptime": self.uptime,
            "peer_count": self.peer_count,
            "task_count": self.task_count,
            "system": self.system.to_dict(),
            "errors": list(self.errors),
        }

    def to_json(self) -> str:
        """Return a compact JSON string."""
        return json.dumps(self.to_dict())


class HealthReporter:
    """
    Produces :class:`HealthSnapshot` instances for a given node.

    Parameters
    ----------
    node_id  : UUID string of the node being monitored.
    registry : Optional node registry (unused internally; available for
               subclasses that want to derive peer counts from it).
    """

    def __init__(self, node_id: str, registry: Any = None) -> None:
        self._node_id = node_id
        self._registry = registry
        self._started_at = time.time()

    # ------------------------------------------------------------------
    # Snapshot construction
    # ------------------------------------------------------------------

    def snapshot(
        self,
        peer_count: int = 0,
        task_count: int = 0,
        errors: list[str] | None = None,
    ) -> HealthSnapshot:
        """
        Collect a health snapshot.

        Status rules
        ------------
        * ``"healthy"``   — zero errors
        * ``"degraded"``  — 1–2 errors
        * ``"unhealthy"`` — 3 or more errors
        """
        errs = list(errors or [])
        n = len(errs)
        if n == 0:
            status = "healthy"
        elif n <= 2:
            status = "degraded"
        else:
            status = "unhealthy"

        return HealthSnapshot(
            node_id=self._node_id,
            timestamp=time.time(),
            status=status,
            uptime=time.time() - self._started_at,
            peer_count=peer_count,
            task_count=task_count,
            system=SystemMetrics.collect(),
            errors=errs,
        )

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    @staticmethod
    def to_http_response(snapshot: HealthSnapshot) -> tuple[int, str]:
        """
        Convert a snapshot to an HTTP status code and JSON body.

        Returns ``(200, json)`` when healthy or degraded, ``(503, json)``
        when unhealthy.
        """
        code = 200 if snapshot.status != "unhealthy" else 503
        return code, snapshot.to_json()

    # ------------------------------------------------------------------
    # Background reporting loop
    # ------------------------------------------------------------------

    async def start_reporting(
        self,
        interval: float = 60.0,
        callback: Callable[[HealthSnapshot], Awaitable[None]] | None = None,
    ) -> None:
        """
        Continuously produce health snapshots and invoke *callback*.

        Runs until the current task is cancelled.
        """
        while True:
            snap = self.snapshot()
            if callback is not None:
                await callback(snap)
            await asyncio.sleep(interval)
