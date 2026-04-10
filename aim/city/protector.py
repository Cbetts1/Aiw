"""
ProtectionAgent — official security bot for the AIM city.

Responsibilities:
- Verify CreatorSignature on incoming nodes and messages
- Detect and blacklist unauthorised nodes
- Monitor the NodeRegistry for rogue entries
- Alert the Governor when threats are detected
- Perform on-demand integrity audits
"""

from __future__ import annotations

import logging
import time
from typing import Any

from aim.node.agent import AgentNode
from aim.identity.ledger import LegacyLedger, default_ledger
from aim.identity.signature import CreatorSignature, ORIGIN_CREATOR
from aim.node.registry import NodeRegistry
from aim.city.roles import CityRole, CityEventKind

logger = logging.getLogger(__name__)


class ProtectionAgent(AgentNode):
    """
    An official Protection Agent for the AIM city.

    Parameters
    ----------
    registry       : NodeRegistry to audit (default: global)
    ledger         : LegacyLedger for event recording (default: global)
    governor_host  : host of the Governor node (for forwarding alerts)
    governor_port  : port of the Governor node
    All other parameters are forwarded to AgentNode / BaseNode.
    """

    ROLE = CityRole.PROTECTOR

    def __init__(
        self,
        *args: Any,
        registry: NodeRegistry | None = None,
        ledger: LegacyLedger | None = None,
        governor_host: str = "127.0.0.1",
        governor_port: int = 7800,
        **kwargs: Any,
    ) -> None:
        caps = list(kwargs.pop("capabilities", None) or [])
        if "protect" not in caps:
            caps = ["protect", "audit", "alert"] + caps
        kwargs["capabilities"] = caps
        super().__init__(*args, **kwargs)

        self._registry      = registry      or NodeRegistry.default()
        self._ledger        = ledger        or default_ledger()
        self._sig           = CreatorSignature(node_id=self.node_id)
        self._governor_host = governor_host
        self._governor_port = governor_port
        self._blacklist:    set[str]              = set()
        self._threat_log:   list[dict[str, Any]] = []

        self.engine.add_rule(
            "protect",
            "I am a Protection Agent. I guard the city against unauthorised access and tampering.",
        )
        self.engine.add_rule(
            "audit",
            "Audits verify all node signatures and detect rogue entries in the registry.",
        )
        self.engine.add_rule(
            "blacklist",
            "Blacklisted nodes are denied all access to city services.",
        )
        self.engine.add_rule(
            "threat",
            "All detected threats are logged and reported to the Governor immediately.",
        )

        self.register_task("audit_registry",   self._task_audit_registry)
        self.register_task("blacklist_node",   self._task_blacklist_node)
        self.register_task("check_signature",  self._task_check_signature)
        self.register_task("threat_report",    self._task_threat_report)

        self._ledger.record(
            CityEventKind.BOT_DEPLOYED,
            self.node_id,
            payload={"role": self.ROLE.value, "capabilities": self.capabilities},
            signature=self._sig,
        )
        logger.info("ProtectionAgent started — node_id=%s", self.node_id[:8])

    # ------------------------------------------------------------------
    # Task handlers
    # ------------------------------------------------------------------

    async def _task_audit_registry(self, args: dict[str, Any]) -> dict[str, Any]:
        """Audit all registered nodes for a valid origin creator."""
        nodes      = self._registry.all_nodes()
        results    = []
        violations = 0
        for rec in nodes:
            valid = rec.creator == ORIGIN_CREATOR
            if not valid:
                violations += 1
                self._threat_log.append({
                    "type":             "invalid_creator",
                    "node_id":          rec.node_id,
                    "declared_creator": rec.creator,
                    "ts":               time.time(),
                })
            results.append({"node_id": rec.node_id, "creator": rec.creator, "valid": valid})

        event_kind = CityEventKind.AUDIT_PASSED if violations == 0 else CityEventKind.AUDIT_FAILED
        self._ledger.record(
            event_kind,
            self.node_id,
            payload={"nodes_checked": len(nodes), "violations": violations},
            signature=self._sig,
        )
        logger.info("Audit complete — %d nodes, %d violations", len(nodes), violations)
        return {
            "status":       "ok",
            "nodes_checked": len(nodes),
            "violations":   violations,
            "results":      results,
            "creator":      self.creator,
        }

    async def _task_blacklist_node(self, args: dict[str, Any]) -> dict[str, Any]:
        node_id = args.get("node_id", "")
        reason  = args.get("reason", "unspecified")
        if not node_id:
            return {"status": "error", "error": "node_id required"}
        self._blacklist.add(node_id)
        self._threat_log.append({
            "type":    "blacklisted",
            "node_id": node_id,
            "reason":  reason,
            "ts":      time.time(),
        })
        self._ledger.record(
            CityEventKind.THREAT_DETECTED,
            node_id,
            payload={"reason": reason, "action": "blacklisted"},
            signature=self._sig,
        )
        logger.warning("Node blacklisted: %s — %s", node_id[:8], reason)
        return {
            "status":      "ok",
            "node_id":     node_id,
            "blacklisted": True,
            "reason":      reason,
            "creator":     self.creator,
        }

    async def _task_check_signature(self, args: dict[str, Any]) -> dict[str, Any]:
        """Verify a CreatorSignature dict supplied by a remote node."""
        sig_dict = args.get("signature", {})
        valid    = False
        try:
            sig   = CreatorSignature.from_dict(dict(sig_dict))
            valid = sig.verify()
        except (ValueError, TypeError, KeyError):
            valid = False

        if not valid:
            self._threat_log.append({"type": "signature_mismatch", "data": sig_dict, "ts": time.time()})
            self._ledger.record(
                CityEventKind.INTEGRITY_VIOLATED,
                self.node_id,
                payload={"sig_dict": sig_dict},
                signature=self._sig,
            )
        else:
            self._ledger.record(
                CityEventKind.INTEGRITY_VERIFIED,
                self.node_id,
                payload={},
                signature=self._sig,
            )
        return {"valid": valid, "creator": self.creator}

    async def _task_threat_report(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "threats":           self._threat_log,
            "blacklisted_count": len(self._blacklist),
            "creator":           self.creator,
        }

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def is_blacklisted(self, node_id: str) -> bool:
        return node_id in self._blacklist
