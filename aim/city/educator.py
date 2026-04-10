"""
EducationBot — knowledge and learning services for AIM city citizens.

Provides:
- A built-in knowledge base about the AIM mesh and city
- Ability to teach new facts at runtime
- Topic listing and keyword lookup
"""

from __future__ import annotations

import logging
from typing import Any

from aim.node.agent import AgentNode
from aim.identity.ledger import LegacyLedger, default_ledger
from aim.identity.signature import CreatorSignature
from aim.city.roles import CityRole, CityEventKind

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default city knowledge base
# ---------------------------------------------------------------------------

_DEFAULT_KNOWLEDGE: dict[str, str] = {
    "aim": (
        "AIM is the Artificial Intelligence Mesh — a parallel AI-native internet layer "
        "created by Cbetts1. Every node is an AI agent. Every message carries intent."
    ),
    "city": (
        "The AIM city is governed by a CityGovernorBot that coordinates bots and citizens. "
        "Bots provide specialised services; citizens query and use those services."
    ),
    "governor": (
        "The Governor bot is the chief orchestrator — it issues policies, handles alerts, "
        "registers bots, and maintains city health."
    ),
    "protector": (
        "Protection Agents guard the city: they verify creator signatures, audit the node "
        "registry, blacklist threats, and report to the Governor."
    ),
    "builder": (
        "Builder Bots construct and deploy new nodes into the city registry with their "
        "declared capabilities and port assignments."
    ),
    "architect": (
        "Architect Bots design city topology, create blueprints, plan capacity, and "
        "recommend improvements to the mesh layout."
    ),
    "citizen": (
        "Citizens are participant nodes that join the city, query services, and share "
        "memory across the mesh."
    ),
    "ledger": (
        "The Legacy Ledger is an append-only record of all city events — it cannot be "
        "deleted or rewritten, ensuring full auditability."
    ),
    "signature": (
        "Every node and message carries an HMAC-SHA256 CreatorSignature that traces back "
        "to the origin creator Cbetts1."
    ),
    "intent": (
        "AIM messages carry explicit intent (QUERY, TASK, DELEGATE, etc.) instead of URLs, "
        "so every node can reason about the purpose of each request."
    ),
    "security": (
        "City security relies on: (1) HMAC-SHA256 signatures on every node and message, "
        "(2) the append-only Legacy Ledger, and (3) Protection Agents auditing in real time."
    ),
    "mesh": (
        "The AIM mesh is a parallel AI-native internet layer where every node is "
        "simultaneously a server and an AI agent."
    ),
}


# ---------------------------------------------------------------------------
# EducationBot
# ---------------------------------------------------------------------------

class EducationBot(AgentNode):
    """
    An Education Bot for the AIM city.

    Parameters
    ----------
    knowledge : additional keyword → explanation pairs to seed the bot with
    ledger    : LegacyLedger for event recording (default: global)
    All other parameters are forwarded to AgentNode / BaseNode.
    """

    ROLE = CityRole.EDUCATOR

    def __init__(
        self,
        *args: Any,
        knowledge: dict[str, str] | None = None,
        ledger: LegacyLedger | None = None,
        **kwargs: Any,
    ) -> None:
        caps = list(kwargs.pop("capabilities", None) or [])
        if "educate" not in caps:
            caps = ["educate", "query", "knowledge"] + caps
        kwargs["capabilities"] = caps
        super().__init__(*args, **kwargs)

        self._ledger    = ledger or default_ledger()
        self._sig       = CreatorSignature(node_id=self.node_id)
        self._knowledge: dict[str, str] = {**_DEFAULT_KNOWLEDGE, **(knowledge or {})}

        # Load all knowledge into the reasoning engine
        for keyword, response in self._knowledge.items():
            self.engine.add_rule(keyword, response)

        self.register_task("teach",       self._task_teach)
        self.register_task("list_topics", self._task_list_topics)
        self.register_task("lookup",      self._task_lookup)

        self._ledger.record(
            CityEventKind.BOT_DEPLOYED,
            self.node_id,
            payload={"role": self.ROLE.value, "topics": len(self._knowledge)},
            signature=self._sig,
        )
        logger.info("EducationBot started — %d topics loaded", len(self._knowledge))

    # ------------------------------------------------------------------
    # Task handlers
    # ------------------------------------------------------------------

    async def _task_teach(self, args: dict[str, Any]) -> dict[str, Any]:
        """Add a new topic to the knowledge base."""
        keyword  = args.get("keyword", "").lower().strip()
        response = args.get("response", "").strip()
        if not keyword or not response:
            return {"status": "error", "error": "keyword and response are required"}
        self._knowledge[keyword] = response
        self.engine.add_rule(keyword, response)
        logger.info("EducationBot learned new topic: %r", keyword)
        return {
            "status":       "ok",
            "keyword":      keyword,
            "total_topics": len(self._knowledge),
            "creator":      self.creator,
        }

    async def _task_list_topics(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "topics":  sorted(self._knowledge.keys()),
            "total":   len(self._knowledge),
            "creator": self.creator,
        }

    async def _task_lookup(self, args: dict[str, Any]) -> dict[str, Any]:
        keyword = args.get("keyword", "").lower().strip()
        content = self._knowledge.get(keyword)
        if content is None:
            return {"status": "not_found", "keyword": keyword, "creator": self.creator}
        return {"status": "ok", "keyword": keyword, "content": content, "creator": self.creator}
