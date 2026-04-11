"""
Tests for aim.gateway.GatewayNode.
"""

from __future__ import annotations

import asyncio
import pytest

from aim.gateway.node import GatewayNode
from aim.identity.ledger import LegacyLedger
from aim.protocol.message import AIMMessage, Intent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gateway(**kwargs) -> GatewayNode:
    ledger = LegacyLedger()
    return GatewayNode(
        host="127.0.0.1",
        port=0,
        ledger=ledger,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Unit tests (no network)
# ---------------------------------------------------------------------------

class TestGatewayNodeInit:
    def test_capabilities_include_gateway(self):
        gw = _make_gateway()
        assert "gateway" in gw.capabilities

    def test_extra_capabilities_preserved(self):
        gw = _make_gateway(capabilities=["custom"])
        assert "gateway" in gw.capabilities
        assert "custom" in gw.capabilities

    def test_relay_peers_stored(self):
        gw = _make_gateway(relay_peers=[("10.0.0.1", 7500)])
        assert ("10.0.0.1", 7500) in gw._relay_peers

    def test_add_relay_at_runtime(self):
        gw = _make_gateway()
        gw.add_relay("10.0.0.2", 7501)
        assert ("10.0.0.2", 7501) in gw._relay_peers

    def test_healthy_relays_empty_before_heartbeat(self):
        gw = _make_gateway(relay_peers=[("127.0.0.1", 7500)])
        # No heartbeat has occurred yet — health is None
        assert gw.healthy_relays() == []

    def test_pick_relay_falls_back_when_no_healthy(self):
        gw = _make_gateway(relay_peers=[("127.0.0.1", 7500)])
        # Falls back to first peer even with no heartbeat
        assert gw._pick_relay() == ("127.0.0.1", 7500)

    def test_pick_relay_returns_none_when_no_peers(self):
        gw = _make_gateway()
        assert gw._pick_relay() is None

    def test_status_dict(self):
        gw = _make_gateway(relay_peers=[("10.0.0.1", 7500)])
        s = gw.status()
        assert s["role"] == "gateway"
        assert "10.0.0.1:7500" in s["relay_peers"]

    def test_creator_origin(self):
        from aim.identity.signature import ORIGIN_CREATOR
        gw = _make_gateway()
        assert gw.creator == ORIGIN_CREATOR


class TestGatewayForwarding:
    """Test message forwarding logic without a live relay."""

    @pytest.mark.asyncio
    async def test_ttl_zero_returns_error(self):
        gw = _make_gateway(relay_peers=[("127.0.0.1", 7500)])
        msg = AIMMessage.query("hello", sender_id="edge-1")
        msg.ttl = 0
        response = await gw._forward_to_relay(msg)
        assert response.payload["result"]["error"] == "ttl_expired"

    @pytest.mark.asyncio
    async def test_no_relay_returns_error(self):
        gw = _make_gateway()  # no relay peers
        msg = AIMMessage.query("hello", sender_id="edge-1")
        response = await gw._forward_to_relay(msg)
        assert response.payload["result"]["error"] == "no_relay_available"

    @pytest.mark.asyncio
    async def test_ttl_decremented_on_forward_attempt(self):
        gw = _make_gateway(relay_peers=[("127.0.0.1", 65535)])  # nothing on port 65535
        msg = AIMMessage.query("hello", sender_id="edge-1")
        original_ttl = msg.ttl
        await gw._forward_to_relay(msg)
        # ttl was decremented before attempting the (failed) send
        assert msg.ttl == original_ttl - 1


class TestGatewayLedgerRecords:
    """Verify that gateway events are recorded in the ledger."""

    @pytest.mark.asyncio
    async def test_ttl_expired_logged(self):
        ledger = LegacyLedger()
        gw = GatewayNode(host="127.0.0.1", port=0, relay_peers=[("127.0.0.1", 7500)], ledger=ledger)
        msg = AIMMessage.query("hi", sender_id="x")
        msg.ttl = 0
        await gw._forward_to_relay(msg)
        kinds = [e.event_kind for e in ledger.all_entries()]
        assert "gateway_message_dropped" in kinds

    @pytest.mark.asyncio
    async def test_forwarded_event_logged_on_attempt(self):
        """When a relay is configured (even if unreachable) a forwarded event is recorded."""
        ledger = LegacyLedger()
        gw = GatewayNode(host="127.0.0.1", port=0, relay_peers=[("127.0.0.1", 65535)], ledger=ledger)
        msg = AIMMessage.query("hi", sender_id="x")
        await gw._forward_to_relay(msg)
        kinds = [e.event_kind for e in ledger.all_entries()]
        assert "gateway_message_forwarded" in kinds
