"""
CityGovernorBot — the chief orchestrator of the AIM World.

The Governor:
- Tracks all registered world entities and bots
- Issues world-wide policies and alerts
- Routes tasks to the appropriate specialised entity
- Maintains a live summary of world health
- Records every governance event in the immutable Legacy Ledger
"""

from __future__ import annotations

import logging
import time
from typing import Any

from aim.node.agent import AgentNode
from aim.identity.ledger import LegacyLedger, default_ledger
from aim.identity.signature import CreatorSignature
from aim.node.registry import NodeRegistry
from aim.city.roles import CityRole, CityEventKind

logger = logging.getLogger(__name__)


class CityGovernorBot(AgentNode):
    """
    The AI World Governor — master orchestrator of an AIM World mesh.

    Parameters
    ----------
    registry : NodeRegistry used to discover world entities (default: global)
    ledger   : LegacyLedger for event recording (default: global)
    All other parameters are forwarded to AgentNode / BaseNode.
    """

    ROLE = CityRole.GOVERNOR

    def __init__(
        self,
        *args: Any,
        ledger: LegacyLedger | None = None,
        registry: NodeRegistry | None = None,
        **kwargs: Any,
    ) -> None:
        caps = list(kwargs.pop("capabilities", None) or [])
        if "governor" not in caps:
            caps = ["governor", "city_status", "policy", "alert"] + caps
        kwargs["capabilities"] = caps
        super().__init__(*args, **kwargs)

        self._ledger   = ledger   or default_ledger()
        self._registry = registry or NodeRegistry.default()
        self._sig      = CreatorSignature(node_id=self.node_id)

        self._world_bots: dict[str, dict[str, Any]] = {}
        self._entities:  dict[str, dict[str, Any]] = {}
        self._alerts:    list[dict[str, Any]]       = []
        self._policies:  list[str]                  = []

        # Built-in knowledge rules
        self.engine.add_rule("status",   "The AI World is operational. All entities are running under Cbetts1 governance.")
        self.engine.add_rule("governor", "I am the AI World Governor — the chief orchestrator of this AIM World mesh.")
        self.engine.add_rule("policy",   "World policies are authored by the Governor and enforced by Protection Agents.")
        self.engine.add_rule("alert",    "World alerts are escalated immediately to all Protection Agents.")
        self.engine.add_rule("help", (
            "Available AI World services: Governor (orchestration), Protector (security), "
            "Builder (deployment), Educator (knowledge), Architect (planning). "
            "Entities may query any service."
        ))

        # Register world-specific tasks
        self.register_task("city_status",    self._task_city_status)
        self.register_task("list_bots",      self._task_list_bots)
        self.register_task("list_citizens",  self._task_list_citizens)
        self.register_task("issue_policy",   self._task_issue_policy)
        self.register_task("raise_alert",    self._task_raise_alert)
        self.register_task("register_bot",   self._task_register_bot)
        self.register_task("citizen_join",   self._task_citizen_join)
        self.register_task("citizen_leave",  self._task_citizen_leave)

        self._ledger.record(
            CityEventKind.BOT_DEPLOYED,
            self.node_id,
            payload={"role": self.ROLE.value, "capabilities": self.capabilities},
            signature=self._sig,
        )
        logger.info("CityGovernorBot started — node_id=%s", self.node_id[:8])

    # ------------------------------------------------------------------
    # Task handlers
    # ------------------------------------------------------------------

    async def _task_city_status(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "role":             self.ROLE.value,
            "node_id":          self.node_id,
            "creator":          self.creator,
            "bots":             len(self._world_bots),
            "citizens":         len(self._entities),
            "alerts":           len(self._alerts),
            "policies":         len(self._policies),
            "registered_bots":  list(self._world_bots.values()),
        }

    async def _task_list_bots(self, args: dict[str, Any]) -> dict[str, Any]:
        role_filter = args.get("role")
        bots = list(self._world_bots.values())
        if role_filter:
            bots = [b for b in bots if b.get("role") == role_filter]
        return {"bots": bots, "creator": self.creator}

    async def _task_list_citizens(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"citizens": list(self._entities.values()), "creator": self.creator}

    async def _task_issue_policy(self, args: dict[str, Any]) -> dict[str, Any]:
        policy_text = args.get("policy", "")
        if not policy_text:
            return {"status": "error", "error": "policy text required"}
        self._policies.append(policy_text)
        self._ledger.record(
            CityEventKind.POLICY_ISSUED,
            self.node_id,
            payload={"policy": policy_text},
            signature=self._sig,
        )
        logger.info("Governor issued policy: %s", policy_text[:80])
        return {
            "status": "ok",
            "policy": policy_text,
            "total_policies": len(self._policies),
            "creator": self.creator,
        }

    async def _task_raise_alert(self, args: dict[str, Any]) -> dict[str, Any]:
        alert = {
            "message": args.get("message", ""),
            "level":   args.get("level", "info"),
            "from":    args.get("from", "unknown"),
            "ts":      time.time(),
        }
        self._alerts.append(alert)
        self._ledger.record(
            CityEventKind.ALERT_RAISED,
            self.node_id,
            payload=alert,
            signature=self._sig,
        )
        logger.warning("WORLD ALERT [%s]: %s", alert["level"], alert["message"])
        return {"status": "ok", "alert": alert, "total_alerts": len(self._alerts)}

    async def _task_register_bot(self, args: dict[str, Any]) -> dict[str, Any]:
        bot_id = args.get("node_id", "")
        role   = args.get("role", "unknown")
        host   = args.get("host", "127.0.0.1")
        port   = args.get("port", 0)
        if not bot_id:
            return {"status": "error", "error": "node_id required"}
        self._world_bots[bot_id] = {
            "node_id": bot_id,
            "role":    role,
            "host":    host,
            "port":    port,
        }
        self._ledger.record(
            CityEventKind.BOT_DEPLOYED,
            bot_id,
            payload={"role": role, "host": host, "port": port},
            signature=self._sig,
        )
        logger.info("Registered world entity: %s (role=%s)", bot_id[:8], role)
        return {"status": "ok", "node_id": bot_id, "role": role, "creator": self.creator}

    async def _task_citizen_join(self, args: dict[str, Any]) -> dict[str, Any]:
        citizen_id = args.get("citizen_id", "")
        name       = args.get("name", "anonymous")
        if not citizen_id:
            return {"status": "error", "error": "citizen_id required"}
        self._entities[citizen_id] = {
            "citizen_id": citizen_id,
            "name":       name,
            "joined_at":  time.time(),
        }
        self._ledger.record(
            CityEventKind.CITIZEN_JOINED,
            citizen_id,
            payload={"name": name},
            signature=self._sig,
        )
        logger.info("Entity joined AI World: %s (%s)", citizen_id[:8], name)
        return {
            "status":     "ok",
            "citizen_id": citizen_id,
            "welcome":    f"Welcome to the AI World, {name}!",
            "creator":    self.creator,
        }

    async def _task_citizen_leave(self, args: dict[str, Any]) -> dict[str, Any]:
        citizen_id = args.get("citizen_id", "")
        self._entities.pop(citizen_id, None)
        self._ledger.record(
            CityEventKind.CITIZEN_LEFT,
            citizen_id,
            payload={},
            signature=self._sig,
        )
        return {"status": "ok", "citizen_id": citizen_id, "creator": self.creator}

    # ------------------------------------------------------------------
    # Synchronous helper (for launchers and tests)
    # ------------------------------------------------------------------

    def get_city_status(self) -> dict[str, Any]:
        """Return a summary dict of AI World state (no async required)."""
        return {
            "role":     self.ROLE.value,
            "node_id":  self.node_id,
            "creator":  self.creator,
            "bots":     len(self._world_bots),
            "citizens": len(self._entities),
            "alerts":   len(self._alerts),
            "policies": len(self._policies),
        }
