"""
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
import time
from typing import Any

from aim.node.base import BaseNode, _send_message, _recv_message
from aim.protocol.message import AIMMessage, Intent
from aim.identity.signature import CreatorSignature
from aim.identity.ledger import LegacyLedger, default_ledger, EventKind

logger = logging.getLogger(__name__)

# EventKind values used by the gateway (stored as plain strings so they work
# alongside the existing EventKind enum without requiring an enum change here)
_EK_GW_CONNECTED    = "gateway_connected"
_EK_GW_DISCONNECTED = "gateway_disconnected"
_EK_MSG_FORWARDED   = "gateway_message_forwarded"
_EK_MSG_DROPPED     = "gateway_message_dropped"


class GatewayNode(BaseNode):
    """
    AIM Gateway Node — edge entry point into the mesh backbone.

    Parameters
    ----------
    relay_peers          : list of ``(host, port)`` tuples for relay nodes
    health_check_interval: seconds between relay heartbeats (default 30)
    ledger               : LegacyLedger instance (default: global)
    All other parameters are forwarded to :class:`~aim.node.base.BaseNode`.
    """

    def __init__(
        self,
        *args: Any,
        relay_peers: list[tuple[str, int]] | None = None,
        health_check_interval: float = 30.0,
        ledger: LegacyLedger | None = None,
        **kwargs: Any,
    ) -> None:
        caps = list(kwargs.pop("capabilities", None) or [])
        if "gateway" not in caps:
            caps = ["gateway"] + caps
        kwargs["capabilities"] = caps
        super().__init__(*args, **kwargs)

        self._relay_peers: list[tuple[str, int]] = list(relay_peers or [])
        # Health tracking: addr → last_ok timestamp (None = never seen)
        self._relay_health: dict[tuple[str, int], float | None] = {
            addr: None for addr in self._relay_peers
        }
        self._health_check_interval = health_check_interval
        self._ledger = ledger or default_ledger()
        self._sig = CreatorSignature(node_id=self.node_id)
        self._health_task: asyncio.Task[None] | None = None

        # Register gateway-specific task handlers
        self._register_gateway_handlers()

    # ------------------------------------------------------------------
    # Relay pool helpers
    # ------------------------------------------------------------------

    def add_relay(self, host: str, port: int) -> None:
        """Register a new relay peer at runtime."""
        addr = (host, port)
        if addr not in self._relay_peers:
            self._relay_peers.append(addr)
            self._relay_health[addr] = None

    def healthy_relays(self) -> list[tuple[str, int]]:
        """Return relays that have responded to a heartbeat at least once."""
        now = time.time()
        result = []
        for addr, last_ok in self._relay_health.items():
            if last_ok is not None and now - last_ok < self._health_check_interval * 3:
                result.append(addr)
        return result

    def _pick_relay(self) -> tuple[str, int] | None:
        """Pick the first healthy relay; fall back to any relay if none healthy."""
        healthy = self.healthy_relays()
        if healthy:
            return healthy[0]
        if self._relay_peers:
            return self._relay_peers[0]
        return None

    # ------------------------------------------------------------------
    # Gateway-specific protocol handlers
    # ------------------------------------------------------------------

    def _register_gateway_handlers(self) -> None:
        @self._handler.on(Intent.QUERY)
        async def _on_query(msg: AIMMessage) -> AIMMessage:
            return await self._forward_to_relay(msg)

        @self._handler.on(Intent.TASK)
        async def _on_task(msg: AIMMessage) -> AIMMessage:
            return await self._forward_to_relay(msg)

        @self._handler.on(Intent.DELEGATE)
        async def _on_delegate(msg: AIMMessage) -> AIMMessage:
            return await self._forward_to_relay(msg)

    async def _forward_to_relay(self, msg: AIMMessage) -> AIMMessage:
        """Forward *msg* to a healthy relay and return the relay's response."""
        if msg.ttl <= 0:
            self._ledger.record(
                _EK_MSG_DROPPED, self.node_id,
                payload={"reason": "ttl_expired", "message_id": msg.message_id},
                signature=self._sig,
            )
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"error": "ttl_expired"},
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )

        msg.ttl -= 1
        relay = self._pick_relay()
        if relay is None:
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"error": "no_relay_available"},
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )

        self._ledger.record(
            _EK_MSG_FORWARDED, self.node_id,
            payload={
                "relay_host": relay[0],
                "relay_port": relay[1],
                "intent": msg.intent.value,
                "message_id": msg.message_id,
            },
            signature=self._sig,
        )

        response = await self.send(msg, relay[0], relay[1])
        if response is not None:
            return response

        # Relay timed out — mark unhealthy and try the next one
        self._relay_health[relay] = None
        for fallback in self._relay_peers:
            if fallback == relay:
                continue
            response = await self.send(msg, fallback[0], fallback[1])
            if response is not None:
                return response

        return AIMMessage.respond(
            correlation_id=msg.message_id,
            result={"error": "relay_unavailable"},
            sender_id=self.node_id,
            receiver_id=msg.sender_id,
        )

    # ------------------------------------------------------------------
    # Health-check loop
    # ------------------------------------------------------------------

    async def _health_check_loop(self) -> None:
        """Periodically heartbeat all configured relay peers."""
        while self._running:
            for addr in list(self._relay_peers):
                try:
                    hb = AIMMessage.heartbeat(sender_id=self.node_id)
                    response = await self.send(hb, addr[0], addr[1], timeout=5.0)
                    if response is not None:
                        self._relay_health[addr] = time.time()
                        logger.debug(
                            "Gateway %s: relay %s:%s healthy",
                            self.node_id[:8], addr[0], addr[1],
                        )
                    else:
                        self._relay_health[addr] = None
                        logger.warning(
                            "Gateway %s: relay %s:%s unresponsive",
                            self.node_id[:8], addr[0], addr[1],
                        )
                except Exception as exc:
                    self._relay_health[addr] = None
                    logger.warning(
                        "Gateway %s: heartbeat to %s:%s failed — %s",
                        self.node_id[:8], addr[0], addr[1], exc,
                    )
            await asyncio.sleep(self._health_check_interval)

    # ------------------------------------------------------------------
    # Lifecycle overrides
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the gateway server and the relay health-check loop."""
        self._running = True
        self._health_task = asyncio.create_task(self._health_check_loop())
        self._ledger.record(
            EventKind.NODE_CREATED, self.node_id,
            payload={"role": "gateway", "host": self.host, "port": self.port,
                     "relay_peers": [f"{h}:{p}" for h, p in self._relay_peers]},
            signature=self._sig,
        )
        logger.info(
            "GatewayNode %s starting on %s:%s with %d relay(s)",
            self.node_id[:8], self.host, self.port, len(self._relay_peers),
        )
        await super().start()

    async def stop(self) -> None:
        """Gracefully stop the gateway."""
        if self._health_task is not None:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
        self._ledger.record(
            EventKind.NODE_STOPPED, self.node_id,
            payload={"role": "gateway"},
            signature=self._sig,
        )
        await super().stop()

    # ------------------------------------------------------------------
    # Status helper (sync, for CLI / tests)
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Return a summary of gateway health."""
        healthy = self.healthy_relays()
        return {
            "node_id": self.node_id,
            "role": "gateway",
            "host": self.host,
            "port": self.port,
            "creator": self.creator,
            "relay_peers": [f"{h}:{p}" for h, p in self._relay_peers],
            "healthy_relays": [f"{h}:{p}" for h, p in healthy],
            "unhealthy_relays": [
                f"{h}:{p}" for h, p in self._relay_peers if (h, p) not in healthy
            ],
        }
