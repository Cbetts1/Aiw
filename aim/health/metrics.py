"""
AIM Health — System-level metrics collected from the stdlib.

``SystemMetrics`` is intentionally lightweight: it reads only from sources
guaranteed to be available on every supported platform (``os``, ``sys``,
``/proc/uptime`` where present).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any


@dataclass
class SystemMetrics:
    """
    Snapshot of system-level metrics.

    Parameters
    ----------
    cpu_count      : Logical CPU count as reported by ``os.cpu_count()``.
    uptime_seconds : System uptime in seconds (0.0 on non-Linux platforms).
    python_version : Full Python version string from ``sys.version``.
    """

    cpu_count: int
    uptime_seconds: float
    python_version: str

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def collect(cls) -> "SystemMetrics":
        """Read metrics from the operating system and return a new snapshot."""
        cpu = os.cpu_count() or 1
        uptime = cls._read_uptime()
        return cls(
            cpu_count=cpu,
            uptime_seconds=uptime,
            python_version=sys.version,
        )

    @staticmethod
    def _read_uptime() -> float:
        """Read ``/proc/uptime`` and return the first field (seconds since boot)."""
        try:
            with open("/proc/uptime", "r") as fh:
                return float(fh.read().split()[0])
        except (OSError, ValueError, IndexError):
            return 0.0

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of this snapshot."""
        return {
            "cpu_count": self.cpu_count,
            "uptime_seconds": self.uptime_seconds,
            "python_version": self.python_version,
        }
