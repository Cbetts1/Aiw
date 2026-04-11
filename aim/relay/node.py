"""
AIM Relay Node — a backbone node that keeps the mesh connected.

RelayNode extends BaseNode with:
- FORWARD intent handler: receives a wrapped message + target address,
  opens a direct connection to the target, and proxies the response back.
- Peer heartbeats: a background task periodically pings relay peers and
  updates RelayRegistry health accordingly.
- Optional response cache: avoids redundant downstream round-trips for
  identical payloads (keyed by a hash of target + inner message).
- LegacyLedger logging: records RELAY_STARTED, RELAY_STOPPED,
  RELAY_FORWARD, and RELAY_HEARTBEAT events.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

from aim.node.base import BaseNode, _send_message, _recv_message
from aim.protocol.message import AIMMessage, Intent, Status
from aim.identity.ledger import LegacyLedger, EventKind, default_ledger
from aim.relay.registry import RelayRegistry, RelayRecord

logger = logging.getLogger(__name__)

# Default interval (seconds) between relay-to-relay heartbeat sweeps
_DEFAULT_HEARTBEAT_INTERVAL = 30.0

# Maximum cached entries (LRU-style eviction when full)
_MAX_CACHE_SIZE = 256


class RelayNode(BaseNode):
    """
    An AIM relay node — a backbone intermediary in the mesh.

    Parameters
    ----------
    relay_registry  : RelayRegistry to register self in and query for peers.
                      Defaults to ``RelayRegistry.default()``.
    ledger          : LegacyLedger for audit logging.
                      Defaults to ``default_ledger()``.
    enable_cache    : if True, cache forwarded responses keyed by
                      (target_host, target_port, inner message digest).
    heartbeat_interval : seconds between peer heartbeat sweeps.
    All remaining kwargs are forwarded to BaseNode.
    """

    def __init__(
        self,
        *args: Any,
        relay_registry: RelayRegistry | None = None,
        ledger: LegacyLedger | None = None,
        enable_cache: bool = True,
        heartbeat_interval: float = _DEFAULT_HEARTBEAT_INTERVAL,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._relay_registry: RelayRegistry = relay_registry or RelayRegistry.default()
        self._ledger: LegacyLedger = ledger or default_ledger()
        self._enable_cache = enable_cache
        self._heartbeat_interval = heartbeat_interval

        # Response cache: cache_key → (timestamp, AIMMessage)
        self._cache: dict[str, tuple[float, AIMMessage]] = {}

        # Background heartbeat task handle
        self._heartbeat_task: asyncio.Task[None] | None = None

        # Register this relay in the relay registry
        self._relay_registry.register(
            RelayRecord(
                relay_id=self.node_id,
                host=self.host,
                port=self.port,
            )
        )

        # Register FORWARD handler on top of built-ins
        self._register_relay_handlers()

    # ------------------------------------------------------------------
    # Protocol handlers
    # ------------------------------------------------------------------

    def _register_relay_handlers(self) -> None:
        @self._handler.on(Intent.FORWARD)
        async def _on_forward(msg: AIMMessage) -> AIMMessage:
            return await self._handle_forward(msg)

    async def _handle_forward(self, msg: AIMMessage) -> AIMMessage:
        """
        Handle a FORWARD message.

        Expected payload keys
        ----------------------
        target_host : str   — destination node host
        target_port : int   — destination node port
        message     : dict  — the inner AIMMessage to deliver (as JSON dict)
        """
        target_host: str = msg.payload.get("target_host", "")
        target_port: int = int(msg.payload.get("target_port", 0))
        inner_raw: dict[str, Any] = msg.payload.get("message", {})

        if not target_host or not target_port:
            logger.warning("Relay %s received FORWARD with missing target", self.node_id[:8])
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"error": "missing target_host or target_port"},
                status=Status.ERROR,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )

        if msg.ttl <= 0:
            logger.warning("Relay %s dropping message with TTL=0", self.node_id[:8])
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"error": "TTL exhausted"},
                status=Status.ERROR,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )

        # Rebuild the inner message
        try:
            inner_raw["intent"] = inner_raw["intent"] if isinstance(inner_raw.get("intent"), str) else inner_raw.get("intent", "query")
            inner_msg = AIMMessage.from_json(json.dumps(inner_raw))
        except Exception as exc:
            logger.warning("Relay %s could not deserialise inner message: %s", self.node_id[:8], exc)
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"error": f"invalid inner message: {exc}"},
                status=Status.ERROR,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )

        # Decrement TTL
        inner_msg.ttl = max(0, msg.ttl - 1)

        # Cache lookup
        cache_key = self._make_cache_key(target_host, target_port, inner_msg)
        if self._enable_cache and cache_key in self._cache:
            _ts, cached_resp = self._cache[cache_key]
            logger.debug("Relay %s cache hit for %s:%s", self.node_id[:8], target_host, target_port)
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"relayed": True, "cached": True, "response": json.loads(cached_resp.to_json())},
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )

        # Forward to target
        response = await self._forward_to(inner_msg, target_host, target_port)

        # Log to ledger
        self._ledger.record(
            EventKind.RELAY_FORWARD,
            self.node_id,
            payload={
                "target": f"{target_host}:{target_port}",
                "inner_intent": inner_msg.intent.value,
                "success": response is not None,
            },
        )

        if response is None:
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"error": f"no response from {target_host}:{target_port}"},
                status=Status.ERROR,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )

        # Store in cache
        if self._enable_cache:
            self._cache_put(cache_key, response)

        return AIMMessage.respond(
            correlation_id=msg.message_id,
            result={"relayed": True, "cached": False, "response": json.loads(response.to_json())},
            sender_id=self.node_id,
            receiver_id=msg.sender_id,
        )

    # ------------------------------------------------------------------
    # Forwarding helper
    # ------------------------------------------------------------------

    async def _forward_to(
        self,
        msg: AIMMessage,
        host: str,
        port: int,
        timeout: float = 5.0,
    ) -> AIMMessage | None:
        """Open a direct connection to (host, port) and deliver *msg*."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=timeout
            )
        except (OSError, asyncio.TimeoutError) as exc:
            logger.warning("Relay %s cannot reach %s:%s — %s", self.node_id[:8], host, port, exc)
            return None

        msg.sender_id = self.node_id
        try:
            await _send_message(writer, msg)
            response = await asyncio.wait_for(_recv_message(reader), timeout=timeout)
            return response
        except asyncio.TimeoutError:
            logger.warning("Relay %s timeout forwarding to %s:%s", self.node_id[:8], host, port)
            return None
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_cache_key(host: str, port: int, msg: AIMMessage) -> str:
        raw = f"{host}:{port}:{msg.intent.value}:{json.dumps(msg.payload, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _cache_put(self, key: str, response: AIMMessage) -> None:
        if len(self._cache) >= _MAX_CACHE_SIZE:
            # Evict the oldest entry
            oldest_key = min(self._cache, key=lambda k: self._cache[k][0])
            del self._cache[oldest_key]
        self._cache[key] = (time.time(), response)

    def cache_invalidate(self) -> None:
        """Clear the entire response cache."""
        self._cache.clear()

    # ------------------------------------------------------------------
    # Peer heartbeats
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        """Periodically send HEARTBEAT to all registered relay peers."""
        while True:
            await asyncio.sleep(self._heartbeat_interval)
            for record in self._relay_registry.all_relays():
                if record.relay_id == self.node_id:
                    continue
                await self._ping_relay(record)

    async def _ping_relay(self, record: RelayRecord) -> None:
        hb = AIMMessage.heartbeat(sender_id=self.node_id)
        response = await self.send(hb, record.host, record.port, timeout=5.0)
        if response is not None:
            self._relay_registry.mark_healthy(record.relay_id)
            self._ledger.record(
                EventKind.RELAY_HEARTBEAT,
                self.node_id,
                payload={
                    "peer_relay": record.relay_id,
                    "peer_addr": f"{record.host}:{record.port}",
                    "alive": True,
                },
            )
            logger.debug(
                "Relay %s heartbeat OK → %s (%s:%s)",
                self.node_id[:8], record.relay_id[:8], record.host, record.port,
            )
        else:
            self._relay_registry.mark_unhealthy(record.relay_id)
            self._ledger.record(
                EventKind.RELAY_HEARTBEAT,
                self.node_id,
                payload={
                    "peer_relay": record.relay_id,
                    "peer_addr": f"{record.host}:{record.port}",
                    "alive": False,
                },
            )
            logger.warning(
                "Relay %s heartbeat FAILED → %s (%s:%s)",
                self.node_id[:8], record.relay_id[:8], record.host, record.port,
            )

    # ------------------------------------------------------------------
    # Lifecycle overrides
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the relay server and background heartbeat loop."""
        self._relay_registry.mark_healthy(self.node_id)
        self._ledger.record(
            EventKind.RELAY_STARTED,
            self.node_id,
            payload={"host": self.host, "port": self.port},
        )
        logger.info(
            "AIM relay %s starting on %s:%s  [creator=%s]",
            self.node_id[:8], self.host, self.port, self.creator,
        )
        self._heartbeat_task = asyncio.ensure_future(self._heartbeat_loop())
        try:
            await super().start()
        finally:
            if self._heartbeat_task is not None:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def stop(self) -> None:
        """Gracefully stop the relay and cancel the heartbeat loop."""
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        self._relay_registry.mark_unhealthy(self.node_id)
        self._ledger.record(EventKind.RELAY_STOPPED, self.node_id)
        await super().stop()
