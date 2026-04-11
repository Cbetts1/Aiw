"""
AIM Gateway Client — connects a private node outbound to a GatewayNode.

The GatewayClient wraps any ``BaseNode`` subclass and establishes a persistent
outbound TCP connection to a public ``GatewayNode``.  Because the connection
originates from the private side, no port-opening or firewall rule is required
on the user's device.

Flow
----
1. ``connect()`` opens a TCP stream to the gateway.
2. It sends an ``ANNOUNCE`` message with ``gateway_register=True`` and the
   node's ``CreatorSignature`` for authentication.
3. The gateway responds with an ACK; the client then enters its read loop.
4. The read loop receives forwarded AIM messages and dispatches them through
   the wrapped node's ``ProtocolHandler``, sending responses back over the
   same connection.
5. A heartbeat task keeps the connection alive.
6. ``disconnect()`` gracefully tears everything down.
"""

from __future__ import annotations

import asyncio
import logging

from aim.protocol.message import AIMMessage, Intent
from aim.identity.signature import CreatorSignature
from aim.node.base import BaseNode, _send_message, _recv_message

logger = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL = 30.0   # seconds between heartbeats


class GatewayClient:
    """
    Connects a private ``BaseNode`` to a public ``GatewayNode`` over an
    outbound TCP connection (no port-opening required on the private side).

    Parameters
    ----------
    node           : the private ``BaseNode`` whose handlers process forwarded
                     messages.
    gateway_host   : hostname or IP of the public gateway.
    gateway_port   : TCP port of the public gateway.
    heartbeat_interval : seconds between liveness pings (default 30 s).
    """

    def __init__(
        self,
        node: BaseNode,
        gateway_host: str,
        gateway_port: int,
        heartbeat_interval: float = _HEARTBEAT_INTERVAL,
    ) -> None:
        self.node = node
        self.gateway_host = gateway_host
        self.gateway_port = gateway_port
        self.heartbeat_interval = heartbeat_interval

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._reader_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Connect / disconnect
    # ------------------------------------------------------------------

    async def connect(self, timeout: float = 10.0) -> bool:
        """
        Establish an outbound connection to the gateway and register this node.

        Returns True on success, False if the connection or registration failed.
        """
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.gateway_host, self.gateway_port),
                timeout=timeout,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            logger.warning(
                "GatewayClient: cannot connect to %s:%s — %s",
                self.gateway_host,
                self.gateway_port,
                exc,
            )
            return False

        # Build registration message: ANNOUNCE with gateway-specific payload
        sig = CreatorSignature(node_id=self.node.node_id)
        reg_msg = AIMMessage.announce(
            capabilities=self.node.capabilities,
            sender_id=self.node.node_id,
        )
        reg_msg.payload["gateway_register"] = True
        reg_msg.payload["signature"] = sig.to_dict()

        try:
            await _send_message(writer, reg_msg)
            ack = await asyncio.wait_for(_recv_message(reader), timeout=timeout)
        except (OSError, asyncio.TimeoutError) as exc:
            logger.warning(
                "GatewayClient: registration with %s:%s failed — %s",
                self.gateway_host,
                self.gateway_port,
                exc,
            )
            writer.close()
            return False

        if ack is None or not ack.payload.get("result", {}).get("registered"):
            logger.warning(
                "GatewayClient: gateway rejected registration (node %s)",
                self.node.node_id[:8],
            )
            writer.close()
            return False

        self._reader = reader
        self._writer = writer
        self._connected = True

        logger.info(
            "GatewayClient: node %s registered with gateway at %s:%s",
            self.node.node_id[:8],
            self.gateway_host,
            self.gateway_port,
        )

        self._reader_task = asyncio.create_task(
            self._read_loop(), name=f"gateway-client-reader-{self.node.node_id[:8]}"
        )
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(),
            name=f"gateway-client-hb-{self.node.node_id[:8]}",
        )
        return True

    async def disconnect(self) -> None:
        """Gracefully close the gateway connection."""
        self._connected = False
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None
        logger.info(
            "GatewayClient: node %s disconnected from gateway",
            self.node.node_id[:8],
        )

    # ------------------------------------------------------------------
    # Background tasks
    # ------------------------------------------------------------------

    async def _read_loop(self) -> None:
        """Receive forwarded AIM messages and dispatch through the node handler."""
        while self._connected and self._reader is not None:
            msg = await _recv_message(self._reader)
            if msg is None:
                self._connected = False
                logger.info(
                    "GatewayClient: connection to gateway dropped (node %s)",
                    self.node.node_id[:8],
                )
                break

            logger.debug(
                "GatewayClient: node %s ← forwarded [%s] from %s",
                self.node.node_id[:8],
                msg.intent,
                msg.sender_id[:8] if msg.sender_id else "?",
            )

            try:
                response = await self.node._handler.dispatch(msg)
            except Exception:
                logger.exception(
                    "GatewayClient: handler raised for intent %s", msg.intent
                )
                response = None

            if response is not None and self._writer is not None:
                try:
                    await _send_message(self._writer, response)
                except OSError:
                    self._connected = False
                    break

    async def _heartbeat_loop(self) -> None:
        """Periodically send heartbeats to keep the gateway connection alive."""
        while self._connected:
            await asyncio.sleep(self.heartbeat_interval)
            if self._connected and self._writer is not None:
                hb = AIMMessage.heartbeat(sender_id=self.node.node_id)
                try:
                    await _send_message(self._writer, hb)
                except OSError:
                    self._connected = False
                    break

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "GatewayClient":
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.disconnect()

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        state = "connected" if self._connected else "disconnected"
        return (
            f"<GatewayClient node={self.node.node_id[:8]} "
            f"gateway={self.gateway_host}:{self.gateway_port} {state}>"
        )
