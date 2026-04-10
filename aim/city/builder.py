"""
BuilderBot — constructs and deploys infrastructure in the AIM city.

Responsibilities:
- Spawn and register new nodes into the city registry
- Prepare node configurations and capability sets
- Track all construction work in the Legacy Ledger
- Provide build-status reports
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from aim.node.agent import AgentNode
from aim.identity.ledger import LegacyLedger, default_ledger
from aim.identity.signature import CreatorSignature
from aim.node.registry import NodeRegistry, NodeRecord
from aim.city.roles import CityRole, CityEventKind

logger = logging.getLogger(__name__)


class BuilderBot(AgentNode):
    """
    A Builder Bot for the AIM city.

    Parameters
    ----------
    registry : NodeRegistry used to register newly built nodes (default: global)
    ledger   : LegacyLedger for event recording (default: global)
    All other parameters are forwarded to AgentNode / BaseNode.
    """

    ROLE = CityRole.BUILDER

    def __init__(
        self,
        *args: Any,
        registry: NodeRegistry | None = None,
        ledger: LegacyLedger | None = None,
        **kwargs: Any,
    ) -> None:
        caps = list(kwargs.pop("capabilities", None) or [])
        if "build" not in caps:
            caps = ["build", "spawn", "deploy"] + caps
        kwargs["capabilities"] = caps
        super().__init__(*args, **kwargs)

        self._registry  = registry or NodeRegistry.default()
        self._ledger    = ledger   or default_ledger()
        self._sig       = CreatorSignature(node_id=self.node_id)
        self._build_log: list[dict[str, Any]] = []

        self.engine.add_rule("build",  "I am the Builder Bot. I construct and register new nodes for the AIM city.")
        self.engine.add_rule("spawn",  "Spawning creates a new node record in the registry, ready to serve tasks.")
        self.engine.add_rule("deploy", "Deployment registers and activates a node with its declared capabilities.")
        self.engine.add_rule("status", "I can report on all construction work completed so far.")

        self.register_task("build_node",    self._task_build_node)
        self.register_task("build_status",  self._task_build_status)
        self.register_task("list_builds",   self._task_list_builds)

        self._ledger.record(
            CityEventKind.BOT_DEPLOYED,
            self.node_id,
            payload={"role": self.ROLE.value, "capabilities": self.capabilities},
            signature=self._sig,
        )
        logger.info("BuilderBot started — node_id=%s", self.node_id[:8])

    # ------------------------------------------------------------------
    # Task handlers
    # ------------------------------------------------------------------

    async def _task_build_node(self, args: dict[str, Any]) -> dict[str, Any]:
        """Register a new node record in the city registry."""
        node_id      = args.get("node_id") or str(uuid.uuid4())
        host         = args.get("host", "127.0.0.1")
        port         = args.get("port", 0)
        capabilities = args.get("capabilities", [])
        role         = args.get("role", "worker")

        if not port:
            return {"status": "error", "error": "port is required"}

        record = NodeRecord(
            node_id=node_id,
            host=host,
            port=port,
            capabilities=capabilities,
            creator=self.creator,
            metadata={"role": role, "built_by": self.node_id},
        )
        self._registry.register(record)

        build_entry = {
            "node_id":      node_id,
            "host":         host,
            "port":         port,
            "role":         role,
            "capabilities": capabilities,
        }
        self._build_log.append(build_entry)
        self._ledger.record(
            CityEventKind.BUILD_COMPLETED,
            node_id,
            payload=build_entry,
            signature=self._sig,
        )
        logger.info("Built node %s at %s:%s (role=%s)", node_id[:8], host, port, role)
        return {
            "status":  "ok",
            "node_id": node_id,
            "host":    host,
            "port":    port,
            "role":    role,
            "creator": self.creator,
        }

    async def _task_build_status(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "builds_completed": len(self._build_log),
            "registry_size":    self._registry.count(),
            "creator":          self.creator,
        }

    async def _task_list_builds(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"builds": self._build_log, "creator": self.creator}
