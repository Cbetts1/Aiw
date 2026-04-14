"""
ArchitectBot — world topology planning and design for the AIM mesh.

Responsibilities:
- Design and document AI World topology blueprints
- Recommend port assignments and node placements
- Analyse the registry for capability gaps
- Maintain a versioned catalogue of desired world structure
"""

from __future__ import annotations

import logging
from typing import Any

from aim.node.agent import AgentNode
from aim.identity.ledger import LegacyLedger, default_ledger
from aim.identity.signature import CreatorSignature
from aim.node.registry import NodeRegistry
from aim.city.roles import CityRole, CityEventKind

logger = logging.getLogger(__name__)

# Required capability tags for a complete city
_REQUIRED_CAPABILITIES = ["governor", "protect", "build", "educate", "design"]


class ArchitectBot(AgentNode):
    """
    An Architect Bot for the AIM World.

    Parameters
    ----------
    registry : NodeRegistry to analyse (default: global)
    ledger   : LegacyLedger for event recording (default: global)
    All other parameters are forwarded to AgentNode / BaseNode.
    """

    ROLE = CityRole.ARCHITECT

    def __init__(
        self,
        *args: Any,
        registry: NodeRegistry | None = None,
        ledger: LegacyLedger | None = None,
        **kwargs: Any,
    ) -> None:
        caps = list(kwargs.pop("capabilities", None) or [])
        if "design" not in caps:
            caps = ["design", "plan", "topology"] + caps
        kwargs["capabilities"] = caps
        super().__init__(*args, **kwargs)

        self._registry   = registry or NodeRegistry.default()
        self._ledger     = ledger   or default_ledger()
        self._sig        = CreatorSignature(node_id=self.node_id)
        self._blueprints: list[dict[str, Any]] = []

        self.engine.add_rule("design",    "I am the Architect Bot. I plan and design the topology of the AIM World.")
        self.engine.add_rule("blueprint", "Blueprints describe the desired node layout, roles, ports, and connections.")
        self.engine.add_rule("topology",  "AI World topology shows all active nodes, their roles, and their connections.")
        self.engine.add_rule("plan",      "I analyse the current registry and recommend capacity improvements.")

        self.register_task("create_blueprint",  self._task_create_blueprint)
        self.register_task("analyse_topology",  self._task_analyse_topology)
        self.register_task("list_blueprints",   self._task_list_blueprints)

        self._ledger.record(
            CityEventKind.BOT_DEPLOYED,
            self.node_id,
            payload={"role": self.ROLE.value, "capabilities": self.capabilities},
            signature=self._sig,
        )
        logger.info("ArchitectBot started — node_id=%s", self.node_id[:8])

    # ------------------------------------------------------------------
    # Task handlers
    # ------------------------------------------------------------------

    async def _task_create_blueprint(self, args: dict[str, Any]) -> dict[str, Any]:
        """Record a new city blueprint."""
        name  = args.get("name", "unnamed")
        nodes = args.get("nodes", [])
        if not nodes:
            return {"status": "error", "error": "nodes list is required"}
        blueprint = {
            "name":        name,
            "nodes":       nodes,
            "designed_by": self.node_id,
            "creator":     self.creator,
        }
        self._blueprints.append(blueprint)
        logger.info("Blueprint created: %s (%d nodes)", name, len(nodes))
        return {"status": "ok", "blueprint": blueprint}

    async def _task_analyse_topology(self, args: dict[str, Any]) -> dict[str, Any]:
        """Analyse the current registry for topology completeness and coverage."""
        all_nodes = self._registry.all_nodes()
        cap_counts: dict[str, int] = {}
        for rec in all_nodes:
            for cap in rec.capabilities:
                cap_counts[cap] = cap_counts.get(cap, 0) + 1

        recommendations = []
        for role_cap in _REQUIRED_CAPABILITIES:
            if cap_counts.get(role_cap, 0) == 0:
                recommendations.append(
                    f"No node with '{role_cap}' capability — deploy one to complete the city."
                )
        if not recommendations:
            recommendations.append("City topology is complete — all required roles are covered.")

        return {
            "total_nodes":               len(all_nodes),
            "capability_distribution":   cap_counts,
            "recommendations":           recommendations,
            "creator":                   self.creator,
        }

    async def _task_list_blueprints(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"blueprints": self._blueprints, "creator": self.creator}
