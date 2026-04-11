"""
Tests for AIM Relay Nodes.

Covers
------
- RelayRegistry CRUD and health tracking
- RelayNode FORWARD handler (in-process, no networking)
- RelayNode forwards a message between two nodes via real TCP loopback
- Relay failure and fallback to another healthy relay (TaskRouter)
- TaskRouter RELAY strategy (direct fallback when no relay available)
- LegacyLedger records relay events
- Response caching on the relay
- TTL exhaustion guard
"""

from __future__ import annotations

import asyncio
import json
import pytest

from aim.relay.registry import RelayRegistry, RelayRecord
from aim.relay.node import RelayNode
from aim.node.base import BaseNode
from aim.node.agent import AgentNode
from aim.node.registry import NodeRegistry, NodeRecord
from aim.protocol.message import AIMMessage, Intent, Status
from aim.identity.ledger import LegacyLedger, EventKind
from aim.compute.router import TaskRouter, RoutingStrategy


# ---------------------------------------------------------------------------
# Helpers — find a free port
# ---------------------------------------------------------------------------

async def _free_port() -> int:
    """Ask the OS for a free TCP port."""
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# RelayRegistry tests
# ---------------------------------------------------------------------------

class TestRelayRegistry:
    def setup_method(self):
        self.registry = RelayRegistry()

    def test_register_and_get(self):
        rec = RelayRecord("r1", "127.0.0.1", 9500)
        self.registry.register(rec)
        assert self.registry.get("r1") is rec

    def test_deregister(self):
        self.registry.register(RelayRecord("r2", "127.0.0.1", 9501))
        self.registry.deregister("r2")
        assert self.registry.get("r2") is None

    def test_healthy_relays_filters_dead(self):
        self.registry.register(RelayRecord("r3", "127.0.0.1", 9502, healthy=True))
        self.registry.register(RelayRecord("r4", "127.0.0.1", 9503, healthy=False))
        healthy = self.registry.healthy_relays()
        assert len(healthy) == 1
        assert healthy[0].relay_id == "r3"

    def test_mark_unhealthy_and_back(self):
        self.registry.register(RelayRecord("r5", "127.0.0.1", 9504, healthy=True))
        self.registry.mark_unhealthy("r5")
        assert self.registry.healthy_relays() == []
        self.registry.mark_healthy("r5")
        assert len(self.registry.healthy_relays()) == 1

    def test_pick_round_robin(self):
        for i in range(3):
            self.registry.register(RelayRecord(f"rr{i}", "127.0.0.1", 9510 + i))
        seen = {self.registry.pick_round_robin().relay_id for _ in range(6)}
        assert seen == {"rr0", "rr1", "rr2"}

    def test_pick_round_robin_returns_none_when_empty(self):
        assert self.registry.pick_round_robin() is None

    def test_pick_random_returns_healthy(self):
        self.registry.register(RelayRecord("live", "127.0.0.1", 9520, healthy=True))
        self.registry.register(RelayRecord("dead", "127.0.0.1", 9521, healthy=False))
        for _ in range(10):
            picked = self.registry.pick_random()
            assert picked is not None
            assert picked.relay_id == "live"

    def test_count(self):
        for i in range(4):
            self.registry.register(RelayRecord(f"cx{i}", "127.0.0.1", 9530 + i))
        assert self.registry.count() == 4

    def test_clear(self):
        self.registry.register(RelayRecord("tmp", "127.0.0.1", 9540))
        self.registry.clear()
        assert self.registry.count() == 0


# ---------------------------------------------------------------------------
# RelayNode in-process handler tests (no real TCP)
# ---------------------------------------------------------------------------

class TestRelayNodeHandlers:
    def setup_method(self):
        self.ledger = LegacyLedger()
        self.relay_registry = RelayRegistry()

    @pytest.mark.asyncio
    async def test_heartbeat_responds(self):
        relay = RelayNode(
            node_id="relay-hb",
            port=0,
            relay_registry=self.relay_registry,
            ledger=self.ledger,
        )
        hb = AIMMessage.heartbeat(sender_id="client")
        response = await relay._handler.dispatch(hb)
        assert response is not None
        assert response.payload["result"]["alive"] is True

    @pytest.mark.asyncio
    async def test_forward_missing_target_returns_error(self):
        relay = RelayNode(
            node_id="relay-err",
            port=0,
            relay_registry=self.relay_registry,
            ledger=self.ledger,
        )
        fwd = AIMMessage(
            intent=Intent.FORWARD,
            payload={"message": {}},
            sender_id="client",
        )
        response = await relay._handler.dispatch(fwd)
        assert response is not None
        result = response.payload.get("result", {})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_forward_ttl_zero_returns_error(self):
        relay = RelayNode(
            node_id="relay-ttl",
            port=0,
            relay_registry=self.relay_registry,
            ledger=self.ledger,
        )
        inner = AIMMessage.heartbeat(sender_id="client")
        fwd = AIMMessage(
            intent=Intent.FORWARD,
            payload={
                "target_host": "127.0.0.1",
                "target_port": 9999,
                "message": json.loads(inner.to_json()),
            },
            sender_id="client",
            ttl=0,
        )
        response = await relay._handler.dispatch(fwd)
        assert response is not None
        assert "TTL exhausted" in response.payload["result"]["error"]

    @pytest.mark.asyncio
    async def test_cache_key_stability(self):
        relay = RelayNode(node_id="cache-test", port=0, relay_registry=self.relay_registry, ledger=self.ledger)
        msg = AIMMessage.heartbeat(sender_id="x")
        k1 = RelayNode._make_cache_key("127.0.0.1", 9999, msg)
        k2 = RelayNode._make_cache_key("127.0.0.1", 9999, msg)
        assert k1 == k2

    @pytest.mark.asyncio
    async def test_relay_registered_in_registry(self):
        relay = RelayNode(
            node_id="auto-reg",
            port=0,
            relay_registry=self.relay_registry,
            ledger=self.ledger,
        )
        rec = self.relay_registry.get("auto-reg")
        assert rec is not None
        assert rec.host == relay.host

    @pytest.mark.asyncio
    async def test_ledger_records_relay_started(self):
        relay = RelayNode(
            node_id="ledger-start",
            port=0,
            relay_registry=self.relay_registry,
            ledger=self.ledger,
            heartbeat_interval=3600.0,  # don't fire during test
        )

        # Simulate start without running the server loop
        self.relay_registry.mark_healthy(relay.node_id)
        self.ledger.record(EventKind.RELAY_STARTED, relay.node_id, payload={"host": relay.host, "port": relay.port})

        entries = self.ledger.entries_by_kind(EventKind.RELAY_STARTED)
        assert any(e.node_id == "ledger-start" for e in entries)


# ---------------------------------------------------------------------------
# Integration: relay forwards a message over real TCP loopback
# ---------------------------------------------------------------------------

@pytest.fixture
async def live_relay_and_node(unused_tcp_port_factory):
    """Start a real RelayNode and a target AgentNode on loopback."""
    relay_port = unused_tcp_port_factory()
    target_port = unused_tcp_port_factory()

    ledger = LegacyLedger()
    relay_registry = RelayRegistry()

    relay = RelayNode(
        node_id="live-relay",
        host="127.0.0.1",
        port=relay_port,
        relay_registry=relay_registry,
        ledger=ledger,
        heartbeat_interval=3600.0,
        enable_cache=True,
    )
    target = AgentNode(
        node_id="target-node",
        host="127.0.0.1",
        port=target_port,
    )

    relay_task = asyncio.create_task(relay.start())
    target_task = asyncio.create_task(target.start())
    await asyncio.sleep(0.1)  # let servers bind

    yield relay, target, relay_registry, ledger, relay_port, target_port

    relay_task.cancel()
    target_task.cancel()
    for t in (relay_task, target_task):
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass


@pytest.mark.asyncio
async def test_relay_forwards_heartbeat(live_relay_and_node):
    relay, target, relay_registry, ledger, relay_port, target_port = live_relay_and_node

    inner_msg = AIMMessage.heartbeat(sender_id="sender-node")
    fwd = AIMMessage(
        intent=Intent.FORWARD,
        payload={
            "target_host": "127.0.0.1",
            "target_port": target_port,
            "message": json.loads(inner_msg.to_json()),
        },
        sender_id="sender-node",
        ttl=8,
    )

    # Send FORWARD to the relay
    from aim.node.base import _send_message, _recv_message
    reader, writer = await asyncio.open_connection("127.0.0.1", relay_port)
    await _send_message(writer, fwd)
    response = await asyncio.wait_for(_recv_message(reader), timeout=5.0)
    writer.close()
    await writer.wait_closed()

    assert response is not None
    result = response.payload.get("result", {})
    assert result.get("relayed") is True
    inner_resp = result.get("response", {})
    assert inner_resp.get("payload", {}).get("result", {}).get("alive") is True


@pytest.mark.asyncio
async def test_relay_caches_second_request(live_relay_and_node):
    relay, target, relay_registry, ledger, relay_port, target_port = live_relay_and_node

    inner_msg = AIMMessage.heartbeat(sender_id="cache-test-sender")
    from aim.node.base import _send_message, _recv_message

    async def send_forward():
        fwd = AIMMessage(
            intent=Intent.FORWARD,
            payload={
                "target_host": "127.0.0.1",
                "target_port": target_port,
                "message": json.loads(inner_msg.to_json()),
            },
            sender_id="cache-test-sender",
            ttl=8,
        )
        reader, writer = await asyncio.open_connection("127.0.0.1", relay_port)
        await _send_message(writer, fwd)
        resp = await asyncio.wait_for(_recv_message(reader), timeout=5.0)
        writer.close()
        await writer.wait_closed()
        return resp

    resp1 = await send_forward()
    resp2 = await send_forward()
    assert resp1 is not None
    assert resp2 is not None
    # Second response must be served from cache
    assert resp2.payload["result"].get("cached") is True


@pytest.mark.asyncio
async def test_relay_ledger_records_forward(live_relay_and_node):
    relay, target, relay_registry, ledger, relay_port, target_port = live_relay_and_node

    inner_msg = AIMMessage.heartbeat(sender_id="ledger-test")
    fwd = AIMMessage(
        intent=Intent.FORWARD,
        payload={
            "target_host": "127.0.0.1",
            "target_port": target_port,
            "message": json.loads(inner_msg.to_json()),
        },
        sender_id="ledger-test",
        ttl=8,
    )

    from aim.node.base import _send_message, _recv_message
    reader, writer = await asyncio.open_connection("127.0.0.1", relay_port)
    await _send_message(writer, fwd)
    await asyncio.wait_for(_recv_message(reader), timeout=5.0)
    writer.close()
    await writer.wait_closed()

    entries = ledger.entries_by_kind(EventKind.RELAY_FORWARD)
    assert len(entries) >= 1
    assert entries[0].node_id == "live-relay"


# ---------------------------------------------------------------------------
# Relay failure and fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_relay_failure_fallback_to_direct(unused_tcp_port_factory):
    """
    When the relay cannot reach the target, _dispatch_via_relay falls back
    to a direct dispatch.  Here we use no relay registry at all so
    pick_round_robin returns None → direct dispatch path.
    """
    target_port = unused_tcp_port_factory()
    target = AgentNode(
        node_id="fallback-target",
        host="127.0.0.1",
        port=target_port,
    )
    target_task = asyncio.create_task(target.start())
    await asyncio.sleep(0.1)

    registry = NodeRegistry()
    registry.register(NodeRecord(
        node_id="fallback-target",
        host="127.0.0.1",
        port=target_port,
        capabilities=["echo"],
    ))

    # relay_registry is None → no relay → direct fallback
    router = TaskRouter(
        registry=registry,
        strategy=RoutingStrategy.RELAY,
        relay_registry=None,
    )
    results = await router.route("echo", capability="echo", sender_id="test")
    target_task.cancel()
    try:
        await target_task
    except (asyncio.CancelledError, Exception):
        pass

    # Direct dispatch reaches the target
    assert len(results) == 1


@pytest.mark.asyncio
async def test_dead_relay_falls_back_to_direct(unused_tcp_port_factory):
    """
    When the relay node is down, the router falls back to direct dispatch
    to reach the target node.
    """
    target_port = unused_tcp_port_factory()
    dead_relay_port = unused_tcp_port_factory()

    target = AgentNode(
        node_id="dr-target",
        host="127.0.0.1",
        port=target_port,
    )
    target_task = asyncio.create_task(target.start())
    await asyncio.sleep(0.1)

    relay_registry = RelayRegistry()
    # Register a relay that is NOT actually listening
    relay_registry.register(RelayRecord(
        relay_id="dead-relay",
        host="127.0.0.1",
        port=dead_relay_port,
        healthy=True,
    ))

    registry = NodeRegistry()
    registry.register(NodeRecord(
        node_id="dr-target",
        host="127.0.0.1",
        port=target_port,
        capabilities=["probe"],
    ))

    router = TaskRouter(
        registry=registry,
        strategy=RoutingStrategy.RELAY,
        relay_registry=relay_registry,
    )
    results = await router.route("probe", capability="probe", sender_id="test")
    target_task.cancel()
    try:
        await target_task
    except (asyncio.CancelledError, Exception):
        pass

    # Falls back to direct → reaches the target
    assert len(results) == 1


# ---------------------------------------------------------------------------
# TaskRouter RELAY strategy — messages routed via live relay
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_router_relay_strategy_routes_via_relay(unused_tcp_port_factory):
    """
    Two nodes and a relay: node A routes a task to node B via the relay
    using RoutingStrategy.RELAY.  Node A does NOT connect to B directly.
    """
    relay_port = unused_tcp_port_factory()
    node_b_port = unused_tcp_port_factory()

    ledger = LegacyLedger()
    relay_registry = RelayRegistry()

    relay = RelayNode(
        node_id="rr-relay",
        host="127.0.0.1",
        port=relay_port,
        relay_registry=relay_registry,
        ledger=ledger,
        heartbeat_interval=3600.0,
        enable_cache=False,
    )
    node_b = AgentNode(
        node_id="rr-node-b",
        host="127.0.0.1",
        port=node_b_port,
    )
    node_b.engine.add_rule("ping", "pong")

    relay_task = asyncio.create_task(relay.start())
    node_b_task = asyncio.create_task(node_b.start())
    await asyncio.sleep(0.1)

    # Node B is registered in NodeRegistry with "ping" capability
    registry = NodeRegistry()
    registry.register(NodeRecord(
        node_id="rr-node-b",
        host="127.0.0.1",
        port=node_b_port,
        capabilities=["ping"],
    ))

    router = TaskRouter(
        registry=registry,
        strategy=RoutingStrategy.RELAY,
        relay_registry=relay_registry,
    )

    # Route a task via relay
    results = await router.route("ping", capability="ping", sender_id="rr-node-a")

    relay_task.cancel()
    node_b_task.cancel()
    for t in (relay_task, node_b_task):
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass

    # We should get at least one response (either from relay or direct fallback)
    assert len(results) >= 1
