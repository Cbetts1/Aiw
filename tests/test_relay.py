"""
Tests for aim.relay.RelayNode.
"""

from __future__ import annotations

import asyncio
import pytest

from aim.relay.node import RelayNode, _LRUCache
from aim.identity.ledger import LegacyLedger
from aim.protocol.message import AIMMessage, Intent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_relay(**kwargs) -> RelayNode:
    ledger = LegacyLedger()
    return RelayNode(
        host="127.0.0.1",
        port=0,
        ledger=ledger,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# _LRUCache unit tests
# ---------------------------------------------------------------------------

class TestLRUCache:
    def test_basic_set_get(self):
        cache = _LRUCache(maxsize=3, ttl=60)
        cache.set("a", 1)
        assert cache.get("a") == 1

    def test_miss_returns_none(self):
        cache = _LRUCache(maxsize=3, ttl=60)
        assert cache.get("missing") is None

    def test_eviction_on_overflow(self):
        cache = _LRUCache(maxsize=2, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)  # "a" should be evicted
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_expired_returns_none(self):
        import time
        cache = _LRUCache(maxsize=10, ttl=0.01)
        cache.set("x", 42)
        time.sleep(0.05)
        assert cache.get("x") is None

    def test_len(self):
        cache = _LRUCache(maxsize=5, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        assert len(cache) == 2


# ---------------------------------------------------------------------------
# RelayNode unit tests
# ---------------------------------------------------------------------------

class TestRelayNodeInit:
    def test_capabilities_include_relay(self):
        relay = _make_relay()
        assert "relay" in relay.capabilities

    def test_extra_capabilities_preserved(self):
        relay = _make_relay(capabilities=["custom"])
        assert "relay" in relay.capabilities
        assert "custom" in relay.capabilities

    def test_relay_peers_stored(self):
        relay = _make_relay(relay_peers=[("10.0.0.1", 7500)])
        assert ("10.0.0.1", 7500) in relay._relay_peers

    def test_add_relay_peer_at_runtime(self):
        relay = _make_relay()
        relay.add_relay_peer("10.0.0.2", 7501)
        assert ("10.0.0.2", 7501) in relay._relay_peers

    def test_healthy_peers_empty_before_heartbeat(self):
        relay = _make_relay(relay_peers=[("127.0.0.1", 7500)])
        assert relay.healthy_relay_peers() == []

    def test_status_dict(self):
        relay = _make_relay(relay_peers=[("10.0.0.1", 7500)])
        s = relay.status()
        assert s["role"] == "relay"
        assert "10.0.0.1:7500" in s["relay_peers"]

    def test_creator_origin(self):
        from aim.identity.signature import ORIGIN_CREATOR
        relay = _make_relay()
        assert relay.creator == ORIGIN_CREATOR


class TestRelayContentCache:
    def test_cache_put_and_get(self):
        relay = _make_relay(content_cache_size=16, content_cache_ttl=60)
        relay.cache_put("cid-1", {"body": "hello"})
        result = relay.cache_get("cid-1")
        assert result == {"body": "hello"}

    def test_cache_miss_returns_none(self):
        relay = _make_relay()
        assert relay.cache_get("nonexistent") is None

    def test_cache_put_records_ledger_event(self):
        ledger = LegacyLedger()
        relay = RelayNode(host="127.0.0.1", port=0, ledger=ledger)
        relay.cache_put("cid-2", {"body": "world"})
        kinds = [e.event_kind for e in ledger.all_entries()]
        assert "relay_content_cached" in kinds


class TestRelayRouting:
    """Test routing logic without live network connections."""

    @pytest.mark.asyncio
    async def test_ttl_zero_returns_error(self):
        relay = _make_relay()
        msg = AIMMessage.query("hi", sender_id="gw-1")
        msg.ttl = 0
        response = await relay._route_message(msg)
        assert response.payload["result"]["error"] == "ttl_expired"

    @pytest.mark.asyncio
    async def test_no_route_returns_error(self):
        relay = _make_relay()
        msg = AIMMessage.query("hi", sender_id="gw-1", receiver_id="unknown-node")
        response = await relay._route_message(msg)
        assert response.payload["result"]["error"] == "no_route_to_receiver"

    @pytest.mark.asyncio
    async def test_ttl_decremented(self):
        relay = _make_relay()
        msg = AIMMessage.query("hi", sender_id="gw-1")
        original_ttl = msg.ttl
        await relay._route_message(msg)
        assert msg.ttl == original_ttl - 1

    @pytest.mark.asyncio
    async def test_announce_learns_route(self):
        relay = _make_relay()
        ann = AIMMessage.announce(capabilities=["query"], sender_id="node-abc")
        ann.payload["addr"] = ["10.0.0.5", 7700]
        await relay._handler.dispatch(ann)
        assert relay._route_table.get("node-abc") == ("10.0.0.5", 7700)


class TestRelayLedgerRecords:
    @pytest.mark.asyncio
    async def test_ttl_dropped_logged(self):
        ledger = LegacyLedger()
        relay = RelayNode(host="127.0.0.1", port=0, ledger=ledger)
        msg = AIMMessage.query("hi", sender_id="x")
        msg.ttl = 0
        await relay._route_message(msg)
        kinds = [e.event_kind for e in ledger.all_entries()]
        assert "relay_message_dropped" in kinds

    def test_add_peer_logged(self):
        ledger = LegacyLedger()
        relay = RelayNode(host="127.0.0.1", port=0, ledger=ledger)
        relay.add_relay_peer("10.0.0.3", 7502)
        kinds = [e.event_kind for e in ledger.all_entries()]
        assert "relay_peer_connected" in kinds
