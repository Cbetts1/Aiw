"""
Meshara Agent Node — a BaseNode with built-in reasoning capabilities.

The agent layer adds:
- A simple rule-based reasoning engine (extensible to LLM backends)
- Task decomposition and subtask spawning
- Cross-node memory sharing
- Conversation context management
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from meshara.protocol.message import MesharaMessage, Intent, Status
from meshara.node.base import BaseNode

logger = logging.getLogger(__name__)


class ReasoningEngine:
    """
    Minimal built-in reasoning engine.

    Rules are matched against the query text in registration order.  The
    first matching rule wins.  An LLM backend can be plugged in by
    subclassing and overriding ``reason``.
    """

    def __init__(self) -> None:
        self._rules: list[tuple[str, str]] = []

    def add_rule(self, keyword: str, response: str) -> None:
        """Register a simple keyword → response rule."""
        self._rules.append((keyword.lower(), response))

    async def reason(self, text: str, context: dict[str, Any]) -> str:
        """Return a response string for the given query text."""
        lower = text.lower()
        for keyword, response in self._rules:
            if keyword in lower:
                return response
        return (
            f"I am a Meshara agent node. I received your query: {text!r}. "
            "No specific rule matched — extend this engine with domain knowledge."
        )


class AgentNode(BaseNode):
    """
    An Meshara node that also acts as an AI agent.

    Parameters
    ----------
    memory      : pre-seeded shared memory key-value store
    All other parameters are forwarded to BaseNode.
    """

    def __init__(
        self,
        *args: Any,
        memory: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.engine = ReasoningEngine()
        self._memory: dict[str, Any] = memory or {}
        self._task_results: dict[str, Any] = {}

        # Register memory handlers on top of built-ins
        self._register_memory_handlers()

    # ------------------------------------------------------------------
    # Memory handlers
    # ------------------------------------------------------------------

    def _register_memory_handlers(self) -> None:
        @self._handler.on(Intent.MEMORY_SET)
        async def _on_memory_set(msg: MesharaMessage) -> MesharaMessage:
            key = msg.payload.get("key")
            value = msg.payload.get("value")
            if key is not None:
                self._memory[key] = value
            return MesharaMessage.respond(
                correlation_id=msg.message_id,
                result={"stored": key},
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )

        @self._handler.on(Intent.MEMORY_GET)
        async def _on_memory_get(msg: MesharaMessage) -> MesharaMessage:
            key = msg.payload.get("key")
            value = self._memory.get(key)
            return MesharaMessage.respond(
                correlation_id=msg.message_id,
                result={"key": key, "value": value},
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )

    # ------------------------------------------------------------------
    # Override BaseNode hooks
    # ------------------------------------------------------------------

    async def on_query(self, text: str, context: dict[str, Any]) -> Any:
        answer = await self.engine.reason(text, context)
        return {
            "answer": answer,
            "node_id": self.node_id,
            "creator": self.creator,
        }

    async def on_task(
        self, name: str, args: dict[str, Any], original_msg: MesharaMessage
    ) -> Any:
        """Execute a named task.  Tasks are looked up by name from a registry."""
        task_fn = self._task_registry.get(name)
        if task_fn is None:
            return {
                "status": "unknown_task",
                "task": name,
                "node_id": self.node_id,
                "creator": self.creator,
            }
        try:
            result = await task_fn(args)
            self._task_results[original_msg.message_id] = result
            return {"status": "ok", "result": result, "creator": self.creator}
        except Exception as exc:
            logger.exception("Task %s failed", name)
            return {"status": "error", "error": str(exc), "creator": self.creator}

    # ------------------------------------------------------------------
    # Task registry
    # ------------------------------------------------------------------

    @property
    def _task_registry(self) -> dict[str, Any]:
        if not hasattr(self, "_tasks"):
            self._tasks: dict[str, Any] = {}
        return self._tasks

    def register_task(self, name: str, fn: Any) -> None:
        """Register a coroutine function as a named executable task."""
        self._task_registry[name] = fn

    # ------------------------------------------------------------------
    # Memory helpers (local)
    # ------------------------------------------------------------------

    def memory_set(self, key: str, value: Any) -> None:
        self._memory[key] = value

    def memory_get(self, key: str, default: Any = None) -> Any:
        return self._memory.get(key, default)

    async def remote_memory_set(
        self, peer_id: str, key: str, value: Any
    ) -> MesharaMessage | None:
        """Write a key-value pair to a remote node's memory."""
        msg = MesharaMessage(
            intent=Intent.MEMORY_SET,
            payload={"key": key, "value": value},
            sender_id=self.node_id,
            receiver_id=peer_id,
        )
        return await self.send_to_peer(peer_id, msg)

    async def remote_memory_get(
        self, peer_id: str, key: str
    ) -> Any:
        """Retrieve a value from a remote node's memory."""
        msg = MesharaMessage(
            intent=Intent.MEMORY_GET,
            payload={"key": key},
            sender_id=self.node_id,
            receiver_id=peer_id,
        )
        response = await self.send_to_peer(peer_id, msg)
        if response is not None:
            return response.payload.get("result", {}).get("value")
        return None
