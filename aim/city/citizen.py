"""
EntityNode — an adoptable AI entity in the AIM world.

Entities can:
- Join and leave the AI World via the Governor
- Query any world service (education, building, architecture, etc.)
- Receive policy updates and alerts
- Store and share personal memory across the mesh
"""

from __future__ import annotations

import logging
from typing import Any

from aim.node.agent import AgentNode
from aim.identity.ledger import LegacyLedger, default_ledger
from aim.identity.signature import CreatorSignature
from aim.city.roles import CityRole, CityEventKind

logger = logging.getLogger(__name__)


class CitizenNode(AgentNode):
    """
    An adoptable AI entity in the AIM World.

    Parameters
    ----------
    name   : human-readable entity name
    ledger : LegacyLedger for event recording (default: global)
    All other parameters are forwarded to AgentNode / BaseNode.
    """

    ROLE = CityRole.CITIZEN

    def __init__(
        self,
        *args: Any,
        name: str = "anonymous",
        ledger: LegacyLedger | None = None,
        **kwargs: Any,
    ) -> None:
        caps = list(kwargs.pop("capabilities", None) or [])
        if "citizen" not in caps:
            caps = ["citizen"] + caps
        kwargs["capabilities"] = caps
        super().__init__(*args, **kwargs)

        self.name    = name
        self._ledger = ledger or default_ledger()
        self._sig    = CreatorSignature(node_id=self.node_id)

        self.engine.add_rule(
            "who am i",
            f"You are AI entity '{name}' in the AIM World, governed by Cbetts1.",
        )
        self.engine.add_rule(
            "aim world",
            "The AIM World is governed by a CityGovernorBot that coordinates entities. "
            "Entities provide specialised services; you can query and use those services.",
        )
        self.engine.add_rule(
            "help",
            "As an AI entity you can query the Governor, Educator, Builder, and Architect. "
            "You can also store personal memory on the mesh.",
        )

        self._ledger.record(
            CityEventKind.CITIZEN_JOINED,
            self.node_id,
            payload={"name": name, "role": self.ROLE.value},
            signature=self._sig,
        )
        logger.info("CitizenNode started — id=%s name=%s", self.node_id[:8], name)

    # ------------------------------------------------------------------
    # Override on_query to include citizen metadata
    # ------------------------------------------------------------------

    async def on_query(self, text: str, context: dict[str, Any]) -> Any:
        answer = await self.engine.reason(text, context)
        return {
            "answer":     answer,
            "citizen_id": self.node_id,
            "name":       self.name,
            "role":       self.ROLE.value,
            "creator":    self.creator,
        }
