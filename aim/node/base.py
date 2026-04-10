"""
AIM Node — base class for every virtual node in the mesh.

Each node is simultaneously a server (accepting inbound AIM messages) and
an agent (capable of reasoning about and executing tasks).  Nodes discover
each other through the NodeRegistry and can delegate work across the mesh.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from aim.protocol.message import AIMMessage, Intent, Status
from aim.protocol.handler import ProtocolHandler
from aim.identity.signature import ORIGIN_CREATOR

logger = logging.getLogger(__name__)

# Wire-level framing: 4-byte big-endian length prefix + UTF-8 JSON payload
_LENGTH_PREFIX_BYTES = 4


async def _send_message(writer: asyncio.StreamWriter, msg: AIMMessage) -> None:
    data = msg.to_bytes()
    length = len(data).to_bytes(_LENGTH_PREFIX_BYTES, "big")
    writer.write(length + data)
    await writer.drain()


async def _recv_message(reader: asyncio.StreamReader) -> AIMMessage | None:
    try:
        raw_len = await reader.readexactly(_LENGTH_PREFIX_BYTES)
        length = int.from_bytes(raw_len, "big")
        raw = await reader.readexactly(length)
        return AIMMessage.from_bytes(raw)
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ValueError):
        return None


class BaseNode:
    """
    A virtual AIM node.

    Parameters
    ----------
    node_id     : unique identifier (auto-generated UUID if omitted)
    host        : bind address for the node server
    port        : TCP port to listen on
    capabilities: list of capability tags this node advertises
    creator     : origin-creator signature propagated on every message
    """

    CREATOR: str = ORIGIN_CREATOR

    def __init__(
        self,
        node_id: str | None = None,
        host: str = "127.0.0.1",
        port: int = 7700,
        capabilities: list[str] | None = None,
        creator: str | None = None,
    ) -> None:
        self.node_id: str = node_id or str(uuid.uuid4())
        self.host = host
        self.port = port
        self.capabilities: list[str] = capabilities or []
        self.creator: str = creator or self.CREATOR

        self._handler = ProtocolHandler()
        self._server: asyncio.Server | None = None
        self._running = False
        self._peers: dict[str, tuple[str, int]] = {}  # node_id → (host, port)

        # Register built-in handlers
        self._register_builtin_handlers()

    # ------------------------------------------------------------------
    # Built-in protocol handlers
    # ------------------------------------------------------------------

    def _register_builtin_handlers(self) -> None:
        @self._handler.on(Intent.HEARTBEAT)
        async def _on_heartbeat(msg: AIMMessage) -> AIMMessage:
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"alive": True, "node_id": self.node_id, "ts": time.time()},
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )

        @self._handler.on(Intent.ANNOUNCE)
        async def _on_announce(msg: AIMMessage) -> None:
            peer_id = msg.sender_id
            if peer_id and peer_id != self.node_id:
                addr = msg.payload.get("addr")
                if isinstance(addr, list) and len(addr) == 2:
                    self._peers[peer_id] = (addr[0], addr[1])
                    logger.info(
                        "Node %s registered peer %s at %s:%s",
                        self.node_id[:8],
                        peer_id[:8],
                        addr[0],
                        addr[1],
                    )
            return None

        @self._handler.on(Intent.QUERY)
        async def _on_query(msg: AIMMessage) -> AIMMessage:
            result = await self.on_query(msg.payload.get("text", ""), msg.context)
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result=result,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )

        @self._handler.on(Intent.TASK)
        async def _on_task(msg: AIMMessage) -> AIMMessage:
            task_name = msg.payload.get("name", "")
            task_args = msg.payload.get("args", {})
            result = await self.on_task(task_name, task_args, msg)
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result=result,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )

    # ------------------------------------------------------------------
    # Override in subclasses
    # ------------------------------------------------------------------

    async def on_query(self, text: str, context: dict[str, Any]) -> Any:
        """Handle a QUERY intent.  Override to add reasoning logic."""
        return {
            "answer": f"Node {self.node_id[:8]} received: {text!r}",
            "node_id": self.node_id,
            "creator": self.creator,
        }

    async def on_task(
        self, name: str, args: dict[str, Any], original_msg: AIMMessage
    ) -> Any:
        """Handle a TASK intent.  Override to add execution logic."""
        return {
            "status": "acknowledged",
            "task": name,
            "node_id": self.node_id,
            "creator": self.creator,
        }

    # ------------------------------------------------------------------
    # Networking
    # ------------------------------------------------------------------

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername")
        logger.debug("Incoming connection from %s", peer)
        try:
            while True:
                msg = await _recv_message(reader)
                if msg is None:
                    break
                logger.debug(
                    "Node %s ← %s [%s]", self.node_id[:8], msg.sender_id[:8] if msg.sender_id else "?", msg.intent
                )
                response = await self._handler.dispatch(msg)
                if response is not None:
                    await _send_message(writer, response)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def send(
        self, msg: AIMMessage, host: str, port: int, timeout: float = 5.0
    ) -> AIMMessage | None:
        """Open a connection to (host, port), send *msg*, return the response."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=timeout
            )
        except (OSError, asyncio.TimeoutError) as exc:
            logger.warning("Cannot connect to %s:%s — %s", host, port, exc)
            return None

        msg.sender_id = self.node_id
        msg.signature = self.creator
        try:
            await _send_message(writer, msg)
            response = await asyncio.wait_for(_recv_message(reader), timeout=timeout)
            return response
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for response from %s:%s", host, port)
            return None
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def send_to_peer(
        self, peer_id: str, msg: AIMMessage
    ) -> AIMMessage | None:
        """Send *msg* to a known peer by its node_id."""
        if peer_id not in self._peers:
            logger.warning("Unknown peer %s", peer_id)
            return None
        host, port = self._peers[peer_id]
        return await self.send(msg, host, port)

    # ------------------------------------------------------------------
    # Announce self to a peer
    # ------------------------------------------------------------------

    async def announce_to(self, host: str, port: int) -> None:
        """Announce this node's presence to a peer at (host, port)."""
        msg = AIMMessage.announce(
            capabilities=self.capabilities,
            sender_id=self.node_id,
        )
        msg.payload["addr"] = [self.host, self.port]
        await self.send(msg, host, port)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start listening for inbound AIM connections."""
        self._server = await asyncio.start_server(
            self._handle_connection, self.host, self.port
        )
        self._running = True
        logger.info(
            "AIM node %s started on %s:%s  [creator=%s]",
            self.node_id[:8],
            self.host,
            self.port,
            self.creator,
        )
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        """Gracefully stop the node."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        self._running = False
        logger.info("AIM node %s stopped", self.node_id[:8])

    def register_handler(self, intent: Intent, fn: Any) -> None:
        """Expose protocol handler registration to subclasses and external code."""
        self._handler.register(intent, fn)

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} id={self.node_id[:8]} "
            f"addr={self.host}:{self.port} creator={self.creator}>"
        )
