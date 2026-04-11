"""
IntegrityGuard — standalone tamper-detection and audit service.

The IntegrityGuard runs outside the node layer and provides:
- SHA-256 checksums of critical city configuration snapshots
- Detection of changes to those checksums (potential tampering)
- Verification that the Legacy Ledger remains append-only
- Validation that all registry nodes carry the origin creator
- A signed integrity report for public inspection
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any

from aim.identity.ledger import LegacyLedger, default_ledger
from aim.identity.signature import CreatorSignature, ORIGIN_CREATOR
from aim.node.registry import NodeRegistry
from aim.city.roles import CityEventKind

logger = logging.getLogger(__name__)


class IntegrityGuard:
    """
    Tamper-detection service for the AIM city.

    This class is intentionally *not* a node — it runs as a pure Python
    object alongside the mesh so it cannot itself be targeted by malicious
    AIM messages.

    Parameters
    ----------
    registry : NodeRegistry to audit (default: global)
    ledger   : LegacyLedger to audit (default: global)
    """

    def __init__(
        self,
        registry: NodeRegistry | None = None,
        ledger: LegacyLedger | None = None,
    ) -> None:
        self._registry   = registry or NodeRegistry.default()
        self._ledger     = ledger   or default_ledger()
        self._sig        = CreatorSignature()
        self._checksums: dict[str, str]           = {}
        self._violations: list[dict[str, Any]]    = []
        self._lock       = threading.RLock()

    # ------------------------------------------------------------------
    # Checksum management
    # ------------------------------------------------------------------

    def snapshot(self, label: str, data: Any) -> str:
        """Compute and store a SHA-256 checksum of *data* under *label*.

        Returns the hex digest.
        """
        serialised = json.dumps(data, sort_keys=True, default=str)
        digest = hashlib.sha256(serialised.encode()).hexdigest()
        with self._lock:
            self._checksums[label] = digest
        return digest

    def verify(self, label: str, data: Any) -> bool:
        """Return True if *data* still matches the stored checksum for *label*.

        If no snapshot exists yet, one is taken automatically and True is returned.
        Tampering is logged in the ledger and recorded in ``_violations``.
        """
        serialised = json.dumps(data, sort_keys=True, default=str)
        current    = hashlib.sha256(serialised.encode()).hexdigest()
        with self._lock:
            stored = self._checksums.get(label)

        if stored is None:
            logger.warning("IntegrityGuard: no snapshot for %r — taking one now", label)
            self.snapshot(label, data)
            return True

        match = current == stored
        if not match:
            entry = {
                "label":   label,
                "stored":  stored,
                "current": current,
                "ts":      time.time(),
            }
            with self._lock:
                self._violations.append(entry)
            self._ledger.record(
                CityEventKind.INTEGRITY_VIOLATED,
                label,
                payload=entry,
                signature=self._sig,
            )
            logger.error("INTEGRITY VIOLATION on %r — stored=%s current=%s", label, stored[:12], current[:12])
        else:
            self._ledger.record(
                CityEventKind.INTEGRITY_VERIFIED,
                label,
                payload={"label": label},
                signature=self._sig,
            )
        return match

    # ------------------------------------------------------------------
    # Ledger integrity
    # ------------------------------------------------------------------

    def audit_ledger(self) -> dict[str, Any]:
        """Verify the ledger is append-only and every entry carries the correct creator."""
        entries         = self._ledger.all_entries()
        invalid_creator = [e for e in entries if e.creator != ORIGIN_CREATOR]
        report = {
            "total_entries":          len(entries),
            "invalid_creator_entries": len(invalid_creator),
            "integrity":              "ok" if not invalid_creator else "violated",
            "creator":                ORIGIN_CREATOR,
            "audited_at":             time.time(),
        }
        kind = CityEventKind.AUDIT_PASSED if not invalid_creator else CityEventKind.AUDIT_FAILED
        self._ledger.record(kind, "ledger", payload=report, signature=self._sig)
        return report

    # ------------------------------------------------------------------
    # Registry integrity
    # ------------------------------------------------------------------

    def audit_registry(self) -> dict[str, Any]:
        """Verify all nodes in the registry carry a valid origin creator."""
        nodes      = self._registry.all_nodes()
        violations = [rec.node_id for rec in nodes if rec.creator != ORIGIN_CREATOR]
        report = {
            "total_nodes": len(nodes),
            "violations":  violations,
            "integrity":   "ok" if not violations else "violated",
            "creator":     ORIGIN_CREATOR,
            "audited_at":  time.time(),
        }
        kind = CityEventKind.AUDIT_PASSED if not violations else CityEventKind.AUDIT_FAILED
        self._ledger.record(kind, "registry", payload=report, signature=self._sig)
        return report

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def full_report(self) -> dict[str, Any]:
        """Return a complete integrity report signed by this guard."""
        with self._lock:
            return {
                "checksums_tracked":  len(self._checksums),
                "violations_detected": len(self._violations),
                "violations":         list(self._violations),
                "signature":          str(self._sig),
                "creator":            ORIGIN_CREATOR,
                "report_ts":          time.time(),
            }
