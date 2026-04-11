"""
AIM Gateway Node — public relay for private AIM nodes behind NAT.

Architecture
------------
* Private nodes establish *outbound* TCP connections to the gateway and send a
  ``ANNOUNCE`` registration message (``gateway_register=True`` in the payload).
  No port-opening on the private side is required.
* The gateway keeps these connections in a routing table keyed by ``node_id``.
* Public clients connect to the gateway, send any AIM message addressed to a
  private ``receiver_id``, and get the forwarded reply transparently.
* Responses from private nodes are matched back to waiting clients via
  ``correlation_id``.

Wire framing
------------
Same 4-byte big-endian length prefix + UTF-8 JSON as the rest of the AIM mesh
(imported from ``aim.node.base``).
GatewayNode — edge-facing entry point into the AIM mesh backbone.

Topology position
-----------------
Edge nodes (phones, browsers, IoT) ──► GatewayNode ──► RelayNode(s)

The gateway maintains a *relay pool* — a list of (host, port) tuples for
relay nodes.  On each forwarded message it picks the first healthy relay
(round-robin).  A background health-check task heartbeats every relay at a
configurable interval.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from aim.protocol.message import AIMMessage, Intent, Status
from aim.identity.signature import CreatorSignature
from aim.identity.ledger import LegacyLedger, EventKind
from aim.node.base import _send_message, _recv_message

logger = logging.getLogger(__name__)

# Gateway-specific ledger event tags (string values extend EventKind without
# requiring enum modification — ``record()`` accepts ``EventKind | str``).
_EV_NODE_REGISTERED   = "gateway_node_registered"
_EV_NODE_DISCONNECTED = "gateway_node_disconnected"
_EV_MSG_FORWARDED     = "gateway_message_forwarded"


# ---------------------------------------------------------------------------
# Internal channel — persistent connection to a registered private node
# ---------------------------------------------------------------------------

class _NodeChannel:
    """
    Maintains a persistent asyncio stream to a registered private node and
    multiplexes concurrent forwarded messages via ``correlation_id`` futures.

    Parameters
    ----------
    node_id      : AIM node identifier of the connected private node.
    gateway_id   : node_id of the GatewayNode (used in heartbeat replies).
    reader/writer: asyncio streams from ``asyncio.start_server``.
    capabilities : capability tags advertised by the private node.
    """

    def __init__(
        self,
        node_id: str,
        gateway_id: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        capabilities: list[str],
    ) -> None:
        self.node_id = node_id
        self.gateway_id = gateway_id
        self.reader = reader
        self.writer = writer
        self.capabilities = capabilities

        self._pending: dict[str, asyncio.Future[AIMMessage]] = {}
        self._send_lock = asyncio.Lock()
        self._reader_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Spawn the background read loop."""
        self._reader_task = asyncio.create_task(
            self._read_loop(), name=f"gateway-channel-{self.node_id[:8]}"
        )

    def close(self) -> None:
        """Cancel the read loop and close the stream."""
        if self._reader_task is not None:
            self._reader_task.cancel()
        self.writer.close()

    # ------------------------------------------------------------------
    # Read loop — runs for the lifetime of the private-node connection
    # ------------------------------------------------------------------

    async def _read_loop(self) -> None:
        try:
            while True:
                msg = await _recv_message(self.reader)
                if msg is None:
                    break

                if msg.intent == Intent.HEARTBEAT:
                    # Reply to keep the channel alive
                    reply = AIMMessage.heartbeat(sender_id=self.gateway_id)
                    try:
                        async with self._send_lock:
                            await _send_message(self.writer, reply)
                    except OSError:
                        break
                    continue

                # Resolve a waiting forward() call
                cid = msg.correlation_id
                if cid and cid in self._pending:
                    fut = self._pending.pop(cid)
                    if not fut.done():
                        fut.set_result(msg)
        finally:
            # Cancel all pending forwarded-message futures
            for fut in self._pending.values():
                if not fut.done():
                    fut.cancel()
            self._pending.clear()

    # ------------------------------------------------------------------
    # Forward a message and await its response
    # ------------------------------------------------------------------

    async def forward(
        self, msg: AIMMessage, timeout: float = 10.0
    ) -> AIMMessage | None:
        """
        Send *msg* to the private node and return its response.

        Returns None on timeout or if the channel is no longer connected.
        """
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[AIMMessage] = loop.create_future()
        self._pending[msg.message_id] = fut
        try:
            async with self._send_lock:
                await _send_message(self.writer, msg)
            return await asyncio.wait_for(fut, timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError, OSError):
            return None
        finally:
            self._pending.pop(msg.message_id, None)


# ---------------------------------------------------------------------------
# GatewayNode — the public relay server
# ---------------------------------------------------------------------------

class GatewayNode:
    """
    A public AIM gateway that relays messages to private nodes behind NAT.

    Private nodes connect *outbound* to this server and register themselves.
    Public clients connect and send messages addressed to a private node; the
    gateway forwards those messages and returns the response.

    Parameters
    ----------
    host    : bind address (default ``"0.0.0.0"`` — all interfaces).
    port    : TCP port to listen on (default ``7900``).
    ledger  : optional ``LegacyLedger`` for event logging; a fresh in-memory
              ledger is created if not provided.
    """

    DEFAULT_PORT = 7900

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = DEFAULT_PORT,
        ledger: LegacyLedger | None = None,
    ) -> None:
        self.node_id: str = str(uuid.uuid4())
        self.host = host
        self.port = port
        self.ledger: LegacyLedger = ledger or LegacyLedger()

        self._routes: dict[str, _NodeChannel] = {}
        self._server: asyncio.Server | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def connected_nodes(self) -> list[str]:
        """Return the node_ids of all currently-connected private nodes."""
        return list(self._routes.keys())

    # ------------------------------------------------------------------
    # Connection handler (entry point for every new TCP connection)
    # ------------------------------------------------------------------

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername")
        logger.debug("Gateway: new connection from %s", peer)
        try:
            msg = await _recv_message(reader)
            if msg is None:
                return

            if (
                msg.intent == Intent.ANNOUNCE
                and msg.payload.get("gateway_register") is True
            ):
                await self._register_node(msg, reader, writer)
            else:
                await self._forward_request(msg, reader, writer)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Private-node registration
    # ------------------------------------------------------------------

    async def _register_node(
        self,
        first_msg: AIMMessage,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        node_id = first_msg.sender_id
        if not node_id:
            logger.warning("Gateway: registration without sender_id — rejected")
            return

        # Verify the CreatorSignature embedded in the registration payload
        sig_dict: dict[str, Any] = first_msg.payload.get("signature", {})
        try:
            sig = CreatorSignature.from_dict({**sig_dict})
            if not sig.verify():
                raise ValueError("digest mismatch")
        except Exception as exc:
            logger.warning(
                "Gateway: invalid signature from %s — %s", node_id[:8], exc
            )
            return

        caps: list[str] = first_msg.payload.get("capabilities", [])
        channel = _NodeChannel(
            node_id=node_id,
            gateway_id=self.node_id,
            reader=reader,
            writer=writer,
            capabilities=caps,
        )
        channel.start()
        self._routes[node_id] = channel

        self.ledger.record(
            _EV_NODE_REGISTERED,
            node_id,
            payload={"capabilities": caps, "gateway": self.node_id},
            signature=sig,
        )
        logger.info(
            "Gateway %s: node %s registered (caps=%s)",
            self.node_id[:8],
            node_id[:8],
            caps,
        )

        # Send ACK so the client can confirm successful registration
        ack = AIMMessage.respond(
            correlation_id=first_msg.message_id,
            result={"registered": True, "gateway_id": self.node_id},
            sender_id=self.node_id,
            receiver_id=node_id,
        )
        try:
            await _send_message(writer, ack)
        except OSError:
            channel.close()
            self._routes.pop(node_id, None)
            return

        # Block here until the private-node connection drops
        if channel._reader_task is not None:
            try:
                await channel._reader_task
            except asyncio.CancelledError:
                pass

        self._routes.pop(node_id, None)
        self.ledger.record(
            _EV_NODE_DISCONNECTED,
            node_id,
            payload={"gateway": self.node_id},
        )
        logger.info(
            "Gateway %s: node %s disconnected", self.node_id[:8], node_id[:8]
        )

    # ------------------------------------------------------------------
    # Client request forwarding
    # ------------------------------------------------------------------

    async def _forward_request(
        self,
        msg: AIMMessage,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        target_id = msg.receiver_id

        if not target_id or target_id not in self._routes:
            error_reply = AIMMessage.respond(
                correlation_id=msg.message_id,
                result={
                    "error": (
                        f"Node {target_id!r} is not connected to this gateway"
                    )
                },
                status=Status.ERROR,
                sender_id=self.node_id,
            )
            try:
                await _send_message(writer, error_reply)
            except OSError:
                pass
            return

        channel = self._routes[target_id]
        response = await channel.forward(msg)

        if response is not None:
            self.ledger.record(
                _EV_MSG_FORWARDED,
                self.node_id,
                payload={
                    "target": target_id,
                    "intent": msg.intent.value,
                    "message_id": msg.message_id,
                },
            )
            try:
                await _send_message(writer, response)
            except OSError:
                pass
        else:
            error_reply = AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"error": "Timeout or target node disconnected"},
                status=Status.ERROR,
                sender_id=self.node_id,
            )
            try:
                await _send_message(writer, error_reply)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start listening for inbound connections."""
        self._server = await asyncio.start_server(
            self._handle_connection, self.host, self.port
        )
        self._running = True
        logger.info(
            "AIM GatewayNode %s started on %s:%s",
            self.node_id[:8],
            self.host,
            self.port,
        )
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        """Gracefully stop the gateway."""
        for channel in list(self._routes.values()):
            channel.close()
        self._routes.clear()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        self._running = False
        logger.info("AIM GatewayNode %s stopped", self.node_id[:8])

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<GatewayNode id={self.node_id[:8]} "
            f"addr={self.host}:{self.port} "
            f"nodes={len(self._routes)}>"
        )
