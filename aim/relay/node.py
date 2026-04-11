"""
RelayNode — backbone routing node for the AIM mesh.

Topology position
-----------------
GatewayNode(s) ──► RelayNode ◄──► RelayNode(s) ──► Compute/Agent Nodes

Responsibilities
----------------
* Accept connections from gateways, other relays, and compute nodes.
* Route ``AIMMessage`` packets by ``receiver_id``; if unknown, broadcast to
  peer relays (learning-switch style).
* Optionally cache recently-read ``ContentItem`` objects (LRU with TTL).
* Perform inter-relay health checks.
* Decrement ``ttl`` on forwarded messages; drop at zero.
* Record significant routing events in the ``LegacyLedger``.
"""

from __future__ import annotations

import asyncio
import collections
import logging
import time
from typing import Any

from aim.node.base import BaseNode, _send_message, _recv_message
from aim.protocol.message import AIMMessage, Intent, Status
from aim.identity.signature import CreatorSignature
from aim.identity.ledger import LegacyLedger, default_ledger, EventKind

logger = logging.getLogger(__name__)

_EK_RELAY_PEER_CONNECTED  = "relay_peer_connected"
_EK_RELAY_MSG_FORWARDED   = "relay_message_forwarded"
_EK_RELAY_MSG_DROPPED     = "relay_message_dropped"
_EK_RELAY_CONTENT_CACHED  = "relay_content_cached"


class _LRUCache:
    """Simple LRU cache with per-entry TTL."""

    def __init__(self, maxsize: int = 256, ttl: float = 300.0) -> None:
        self._maxsize = maxsize
        self._ttl = ttl
        self._store: collections.OrderedDict[str, tuple[Any, float]] = (
            collections.OrderedDict()
        )

    def get(self, key: str) -> Any | None:
        if key not in self._store:
            return None
        value, expires = self._store[key]
        if time.time() > expires:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (value, time.time() + self._ttl)
        while len(self._store) > self._maxsize:
            self._store.popitem(last=False)

    def __len__(self) -> int:
        return len(self._store)


class RelayNode(BaseNode):
    """
    AIM Relay Node — backbone router.

    Parameters
    ----------
    relay_peers           : list of ``(host, port)`` tuples for peer relays
    health_check_interval : seconds between relay-peer heartbeats (default 60)
    content_cache_size    : max items in the relay content cache (default 256)
    content_cache_ttl     : seconds before a cached item expires (default 300)
    ledger                : LegacyLedger instance (default: global)
    All other parameters are forwarded to :class:`~aim.node.base.BaseNode`.
    """

    def __init__(
        self,
        *args: Any,
        relay_peers: list[tuple[str, int]] | None = None,
        health_check_interval: float = 60.0,
        content_cache_size: int = 256,
        content_cache_ttl: float = 300.0,
        ledger: LegacyLedger | None = None,
        **kwargs: Any,
    ) -> None:
        caps = list(kwargs.pop("capabilities", None) or [])
        if "relay" not in caps:
            caps = ["relay"] + caps
        kwargs["capabilities"] = caps
        super().__init__(*args, **kwargs)

        self._relay_peers: list[tuple[str, int]] = list(relay_peers or [])
        self._relay_health: dict[tuple[str, int], float | None] = {
            addr: None for addr in self._relay_peers
        }
        self._health_check_interval = health_check_interval
        self._content_cache = _LRUCache(
            maxsize=content_cache_size, ttl=content_cache_ttl
        )
        self._ledger = ledger or default_ledger()
        self._sig = CreatorSignature(node_id=self.node_id)
        self._health_task: asyncio.Task[None] | None = None

        # Routing table: receiver_id → (host, port)
        self._route_table: dict[str, tuple[str, int]] = {}

        self._register_relay_handlers()

    # ------------------------------------------------------------------
    # Relay peer management
    # ------------------------------------------------------------------

    def add_relay_peer(self, host: str, port: int) -> None:
        """Register a new relay peer at runtime."""
        addr = (host, port)
        if addr not in self._relay_peers:
            self._relay_peers.append(addr)
            self._relay_health[addr] = None
            self._ledger.record(
                _EK_RELAY_PEER_CONNECTED, self.node_id,
                payload={"peer_host": host, "peer_port": port},
                signature=self._sig,
            )

    def healthy_relay_peers(self) -> list[tuple[str, int]]:
        """Return peer relays with a recent heartbeat."""
        now = time.time()
        return [
            addr for addr, last_ok in self._relay_health.items()
            if last_ok is not None and now - last_ok < self._health_check_interval * 3
        ]

    # ------------------------------------------------------------------
    # Content cache helpers (used by ContentLayer integration)
    # ------------------------------------------------------------------

    def cache_put(self, content_id: str, item: Any) -> None:
        """Store a content item in the relay's LRU cache."""
        self._content_cache.set(content_id, item)
        self._ledger.record(
            _EK_RELAY_CONTENT_CACHED, self.node_id,
            payload={"content_id": content_id},
            signature=self._sig,
        )

    def cache_get(self, content_id: str) -> Any | None:
        """Retrieve a cached content item, or None on miss / expiry."""
        return self._content_cache.get(content_id)

    # ------------------------------------------------------------------
    # Relay-specific protocol handlers
    # ------------------------------------------------------------------

    def _register_relay_handlers(self) -> None:
        """Register forwarding handlers for routable intents."""
        for intent in (Intent.QUERY, Intent.TASK, Intent.DELEGATE):
            # Capture intent in closure
            def _make_handler(i: Intent):  # noqa: ANN001
                async def _handler(msg: AIMMessage) -> AIMMessage:
                    return await self._route_message(msg)
                return _handler
            self._handler.register(intent, _make_handler(intent))

        @self._handler.on(Intent.ANNOUNCE)
        async def _on_announce(msg: AIMMessage) -> None:
            # Learn the sender's address for future routing
            addr = msg.payload.get("addr")
            if isinstance(addr, list) and len(addr) == 2 and msg.sender_id:
                self._route_table[msg.sender_id] = (addr[0], addr[1])
                logger.debug(
                    "Relay %s learned route: %s → %s:%s",
                    self.node_id[:8], msg.sender_id[:8], addr[0], addr[1],
                )
            return None

    async def _route_message(self, msg: AIMMessage) -> AIMMessage:
        """Route *msg* to its intended receiver or broadcast to peers."""
        if msg.ttl <= 0:
            self._ledger.record(
                _EK_RELAY_MSG_DROPPED, self.node_id,
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

        # Try the route table first
        receiver_id = msg.receiver_id
        if receiver_id and receiver_id in self._route_table:
            host, port = self._route_table[receiver_id]
            response = await self.send(msg, host, port)
            if response is not None:
                self._ledger.record(
                    _EK_RELAY_MSG_FORWARDED, self.node_id,
                    payload={
                        "to_host": host, "to_port": port,
                        "intent": msg.intent.value,
                        "message_id": msg.message_id,
                    },
                    signature=self._sig,
                )
                return response

        # Fan out to healthy peer relays
        for addr in self.healthy_relay_peers():
            response = await self.send(msg, addr[0], addr[1])
            if response is not None:
                return response

        # No route found
        return AIMMessage.respond(
            correlation_id=msg.message_id,
            result={"error": "no_route_to_receiver"},
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
                    else:
                        self._relay_health[addr] = None
                        logger.warning(
                            "Relay %s: peer %s:%s unresponsive",
                            self.node_id[:8], addr[0], addr[1],
                        )
                except Exception as exc:
                    self._relay_health[addr] = None
                    logger.warning(
                        "Relay %s: heartbeat to %s:%s failed — %s",
                        self.node_id[:8], addr[0], addr[1], exc,
                    )
            await asyncio.sleep(self._health_check_interval)

    # ------------------------------------------------------------------
    # Lifecycle overrides
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the relay server and the peer health-check loop."""
        self._running = True
        self._health_task = asyncio.create_task(self._health_check_loop())
        self._ledger.record(
            EventKind.NODE_CREATED, self.node_id,
            payload={"role": "relay", "host": self.host, "port": self.port,
                     "relay_peers": [f"{h}:{p}" for h, p in self._relay_peers]},
            signature=self._sig,
        )
        logger.info(
            "RelayNode %s starting on %s:%s with %d peer relay(s)",
            self.node_id[:8], self.host, self.port, len(self._relay_peers),
        )
        await super().start()

    async def stop(self) -> None:
        """Gracefully stop the relay."""
        if self._health_task is not None:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
        self._ledger.record(
            EventKind.NODE_STOPPED, self.node_id,
            payload={"role": "relay"},
            signature=self._sig,
        )
        await super().stop()

    # ------------------------------------------------------------------
    # Status helper (sync, for CLI / tests)
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Return a summary of relay health."""
        healthy = self.healthy_relay_peers()
        return {
            "node_id": self.node_id,
            "role": "relay",
            "host": self.host,
            "port": self.port,
            "creator": self.creator,
            "relay_peers": [f"{h}:{p}" for h, p in self._relay_peers],
            "healthy_peers": [f"{h}:{p}" for h, p in healthy],
            "route_table_size": len(self._route_table),
            "cache_size": len(self._content_cache),
        }
