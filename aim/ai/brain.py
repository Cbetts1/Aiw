"""
AIM AIBrain — the built-in intelligence layer for the web bridge.

AIBrain provides:
- Local rule-based and pattern-matched responses (zero dependencies).
- Optional forwarding of queries to a registered remote AIM node.
- Session tracking so follow-up questions retain context.
- Connection management: nodes are registered here AND stored as
  VirtualServer resources in VCloudManager so every connected AI is
  traceable and manageable through the virtual-cloud API.

Usage (from web/server.py)
--------------------------
    brain = AIBrain.default()
    result = await brain.query("what is the mesh?", session_id="abc")
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from aim import __version__, __origin__
from aim.node.base import _send_message, _recv_message
from aim.protocol.message import AIMMessage
from aim.vcloud.manager import VCloudManager
from aim.vcloud.resource import ResourceKind

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in knowledge base (keyword → response)
# ---------------------------------------------------------------------------

_KNOWLEDGE: list[tuple[str, str]] = [
    ("what is aim",
     "A.I.M. (Artificial Intelligence Mesh) is a parallel AI-native internet layer "
     "designed to run alongside the World Wide Web. Every node is an AI agent that "
     "can reason, collaborate, and delegate work across the mesh."),
    ("what is the mesh",
     "The AIM Mesh is a decentralised network of AI agent nodes. Unlike HTTP servers "
     "that serve static pages, mesh nodes carry *intent* — they understand what is "
     "being asked and respond intelligently."),
    ("who created aim",
     f"A.I.M. was founded by {__origin__}. "
     "Free forever. Never for sale. Never for profit."),
    ("what is aura",
     "The Aura Project is the stewarding organisation of A.I.M. It governs the "
     "foundational mesh protocol and ensures AIM stays open and free for everyone."),
    ("how do i connect",
     "Start a gateway: `aim gateway start --host 0.0.0.0 --port 7900`. "
     "Then connect any node: `aim node connect-gateway --host <ip> --port 7900`. "
     "Or use `aim mesh up --with-gateway --with-relay` to spin up a full local stack."),
    ("how do i start",
     "Run `aim web start` to launch the web bridge on port 8080. "
     "From there you can query nodes, manage connections, and explore the mesh."),
    ("what is a node",
     "An AIM node is a lightweight AI agent process. It listens on a TCP port, "
     "accepts AIM protocol messages, and responds with reasoned results. "
     "Start one with `aim node start --port 7700`."),
    ("what is the gateway",
     "The AIM Gateway is a public-facing relay point that lets nodes behind firewalls "
     "or on remote networks connect into the mesh. Start one with "
     "`aim gateway start --host 0.0.0.0 --port 7900`."),
    ("what is vcloud",
     "Virtual Cloud (vcloud) is AIM's built-in compute layer. Every remote connection "
     "is automatically stored as a VirtualServer in vcloud so you can track, allocate, "
     "and manage compute resources across the entire mesh from one place."),
    ("version",
     f"AIM version {__version__} — origin creator {__origin__}."),
    ("hello",
     "Hello! I'm the AIM AI. Ask me anything about the Artificial Intelligence Mesh, "
     "how to connect nodes, or what the system can do."),
    ("hi ",
     "Hi there! I'm the AIM AI — your command-center intelligence. "
     "What would you like to know?"),
    ("help",
     "I can answer questions about AIM, show you how to connect nodes, explain the "
     "mesh architecture, and query any registered remote node. Try asking: "
     "'what is aim', 'how do i connect', or 'list connections'."),
]


# ---------------------------------------------------------------------------
# AIBrain
# ---------------------------------------------------------------------------

class AIBrain:
    """
    The built-in AI reasoning engine for the AIM web bridge.

    Parameters
    ----------
    vcloud : VCloudManager used to persist remote-node connections.
    """

    _default: "AIBrain | None" = None

    def __init__(self, vcloud: VCloudManager | None = None) -> None:
        self._vcloud = vcloud or VCloudManager.default()
        # session_id → list of {"role": "user"|"ai", "text": str, "ts": float}
        self._sessions: dict[str, list[dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def default(cls) -> "AIBrain":
        if cls._default is None:
            cls._default = cls()
        return cls._default

    # ------------------------------------------------------------------
    # Core query
    # ------------------------------------------------------------------

    async def query(
        self,
        text: str,
        session_id: str | None = None,
        node_host: str | None = None,
        node_port: int | None = None,
    ) -> dict[str, Any]:
        """
        Process a query and return a result dict.

        If *node_host* / *node_port* are given the query is also forwarded
        to that remote AIM node and the remote result is merged in.
        Otherwise the built-in knowledge base answers.

        Returns
        -------
        dict with keys: answer, session_id, source, remote (optional)
        """
        sid = session_id or str(uuid.uuid4())
        history = self._sessions.setdefault(sid, [])
        history.append({"role": "user", "text": text, "ts": time.time()})

        local_answer = self._local_reason(text, history)
        result: dict[str, Any] = {
            "answer":     local_answer,
            "session_id": sid,
            "source":     "local",
            "version":    __version__,
        }

        # Optionally forward to a remote AIM node
        if node_host and node_port:
            remote = await self._query_remote(text, node_host, node_port)
            if remote is not None:
                result["remote"] = remote
                result["source"] = "hybrid"

        history.append({"role": "ai", "text": result["answer"], "ts": time.time()})
        # Keep last 40 turns per session
        if len(history) > 40:
            self._sessions[sid] = history[-40:]

        return result

    # ------------------------------------------------------------------
    # Remote-node forwarding
    # ------------------------------------------------------------------

    async def _query_remote(
        self, text: str, host: str, port: int, timeout: float = 8.0
    ) -> dict[str, Any] | None:
        """Forward *text* to a remote AIM node and return its payload."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=timeout
            )
            msg = AIMMessage.query(text, sender_id="aim-brain")
            await _send_message(writer, msg)
            response = await asyncio.wait_for(_recv_message(reader), timeout=timeout)
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            if response is not None:
                return response.payload.get("result", response.payload)
        except (ConnectionRefusedError, OSError, asyncio.TimeoutError) as exc:
            logger.warning("AIBrain: remote node %s:%s unreachable — %s", host, port, exc)
        return None

    # ------------------------------------------------------------------
    # Local reasoning
    # ------------------------------------------------------------------

    def _local_reason(self, text: str, history: list[dict[str, Any]]) -> str:
        lower = text.lower().strip()

        # Greet by name if we know them from prior context
        if lower in ("hello", "hi", "hey"):
            return (
                "Hello! I'm the AIM AI — the intelligence layer of the "
                "Artificial Intelligence Mesh command center. "
                "Ask me anything or type 'help' for guidance."
            )

        for keyword, response in _KNOWLEDGE:
            if keyword in lower:
                return response

        # Context-aware fallback
        if history and len(history) > 2:
            return (
                f"I received: \"{text}\". I don't have a specific answer built in, "
                "but I'm connected to the AIM Mesh. If you have a remote node running, "
                "add it under Connections and I'll forward your queries there."
            )

        return (
            f"I'm the AIM AI. I received: \"{text}\". "
            "I don't have a built-in answer for that yet. "
            "Try: 'what is aim', 'how do i connect', 'what is vcloud', or 'help'."
        )

    # ------------------------------------------------------------------
    # Connection / vcloud management
    # ------------------------------------------------------------------

    def register_connection(
        self,
        name: str,
        host: str,
        port: int,
        capabilities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Register a remote AIM node connection and persist it to vcloud.

        Returns the VirtualServer dict.
        """
        meta = dict(metadata or {})
        meta["aim_connection"] = True
        meta["capabilities"] = capabilities or ["query", "task"]
        vs = self._vcloud.create_vserver(
            name=name or f"aim-node-{host}-{port}",
            host=host,
            port=port,
            metadata=meta,
        )
        logger.info("AIBrain: registered connection %s (%s:%s) → vcloud %s",
                    name, host, port, vs.resource_id)
        return vs.to_dict()

    def list_connections(self) -> list[dict[str, Any]]:
        """Return all vcloud VirtualServer resources tagged as AIM connections."""
        return [
            r.to_dict()
            for r in self._vcloud.by_kind(ResourceKind.VSERVER)
            if r.metadata.get("aim_connection")
        ]

    def remove_connection(self, resource_id: str) -> bool:
        """Destroy a connection by its vcloud resource_id. Returns True if found."""
        r = self._vcloud.get(resource_id)
        if r is None or not r.metadata.get("aim_connection"):
            return False
        self._vcloud.destroy(resource_id)
        return True

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def clear_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def session_history(self, session_id: str) -> list[dict[str, Any]]:
        return list(self._sessions.get(session_id, []))

    def status(self) -> dict[str, Any]:
        connections = self.list_connections()
        return {
            "ai":          "AIM Brain",
            "version":     __version__,
            "origin":      __origin__,
            "sessions":    len(self._sessions),
            "connections": len(connections),
            "knowledge_rules": len(_KNOWLEDGE),
        }
