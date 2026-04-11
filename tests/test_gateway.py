"""
Tests for the AIM Gateway module.

Covers:
* Node registers with a GatewayNode.
* Public client sends a QUERY via the gateway to a private node and gets a response.
* Gateway logs events to the LegacyLedger.
* GatewayClient correctly dispatches forwarded messages through the node handler.
* Error response when targeting an unregistered node.
"""

from __future__ import annotations

import asyncio
import pytest

from aim.gateway.node import GatewayNode, _EV_NODE_REGISTERED, _EV_MSG_FORWARDED
from aim.gateway.client import GatewayClient
from aim.node.agent import AgentNode
from aim.node.base import BaseNode, _send_message, _recv_message
from aim.identity.ledger import LegacyLedger
from aim.protocol.message import AIMMessage, Intent, Status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _start_gateway(gw: GatewayNode) -> asyncio.Task:
    """Start a GatewayNode in the background and return its task."""
    task = asyncio.create_task(gw.start())
    # Give the server a moment to bind
    await asyncio.sleep(0.05)
    return task


async def _stop_gateway(gw: GatewayNode, task: asyncio.Task) -> None:
    """Stop the gateway and cancel its serve-forever task."""
    await gw.stop()
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


async def _send_and_recv(
    host: str, port: int, msg: AIMMessage, timeout: float = 5.0
) -> AIMMessage | None:
    """Open a raw TCP connection, send *msg*, return the response."""
    reader, writer = await asyncio.open_connection(host, port)
    try:
        await _send_message(writer, msg)
        return await asyncio.wait_for(_recv_message(reader), timeout=timeout)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# GatewayNode — unit-level tests (no GatewayClient)
# ---------------------------------------------------------------------------

class TestGatewayNodeRegistration:
    async def test_node_registers_successfully(self):
        """A private node that connects with a valid signature is accepted."""
        ledger = LegacyLedger()
        gw = GatewayNode(host="127.0.0.1", port=17900, ledger=ledger)
        gw_task = await _start_gateway(gw)

        private_node = AgentNode(node_id="private-reg", capabilities=["query"])
        client = GatewayClient(private_node, "127.0.0.1", 17900)
        try:
            ok = await client.connect()
            assert ok is True
            assert "private-reg" in gw.connected_nodes
        finally:
            await client.disconnect()
            await _stop_gateway(gw, gw_task)

    async def test_registration_logged_in_ledger(self):
        """Successful registration emits a ledger entry."""
        ledger = LegacyLedger()
        gw = GatewayNode(host="127.0.0.1", port=17901, ledger=ledger)
        gw_task = await _start_gateway(gw)

        node = AgentNode(node_id="reg-ledger")
        client = GatewayClient(node, "127.0.0.1", 17901)
        try:
            await client.connect()
            await asyncio.sleep(0.05)

            entries = ledger.entries_by_kind(_EV_NODE_REGISTERED)
            assert len(entries) == 1
            assert entries[0].node_id == "reg-ledger"
        finally:
            await client.disconnect()
            await _stop_gateway(gw, gw_task)

    async def test_unregistered_target_returns_error(self):
        """Query addressed to a node not connected to the gateway returns an error."""
        ledger = LegacyLedger()
        gw = GatewayNode(host="127.0.0.1", port=17902, ledger=ledger)
        gw_task = await _start_gateway(gw)

        msg = AIMMessage.query("hello?", sender_id="cli", receiver_id="ghost-node")
        try:
            response = await _send_and_recv("127.0.0.1", 17902, msg)
            assert response is not None
            result = response.payload.get("result", {})
            assert "not connected" in result.get("error", "").lower() or \
                   "ghost-node" in result.get("error", "")
        finally:
            await _stop_gateway(gw, gw_task)


# ---------------------------------------------------------------------------
# End-to-end: public client → gateway → private node
# ---------------------------------------------------------------------------

class TestGatewayForwarding:
    async def test_query_forwarded_to_private_node(self):
        """A QUERY sent via the gateway reaches the private node and returns its answer."""
        ledger = LegacyLedger()
        gw = GatewayNode(host="127.0.0.1", port=17910, ledger=ledger)
        gw_task = await _start_gateway(gw)

        private_node = AgentNode(node_id="private-query", capabilities=["query"])
        private_node.engine.add_rule("aim", "AIM is the Artificial Intelligence Mesh.")
        client = GatewayClient(private_node, "127.0.0.1", 17910)
        try:
            await client.connect()
            await asyncio.sleep(0.05)

            # Public client sends a query targeted at the private node
            msg = AIMMessage.query(
                "What is AIM?",
                sender_id="public-client",
                receiver_id="private-query",
            )
            response = await _send_and_recv("127.0.0.1", 17910, msg)

            assert response is not None
            assert response.intent == Intent.RESPOND
            result = response.payload.get("result", {})
            assert "Artificial Intelligence Mesh" in result.get("answer", "")
        finally:
            await client.disconnect()
            await _stop_gateway(gw, gw_task)

    async def test_task_forwarded_to_private_node(self):
        """A TASK sent via the gateway is executed by the private node."""
        ledger = LegacyLedger()
        gw = GatewayNode(host="127.0.0.1", port=17911, ledger=ledger)
        gw_task = await _start_gateway(gw)

        private_node = AgentNode(node_id="private-task")

        async def triple(args: dict) -> int:
            return args["n"] * 3

        private_node.register_task("triple", triple)
        client = GatewayClient(private_node, "127.0.0.1", 17911)
        try:
            await client.connect()
            await asyncio.sleep(0.05)

            msg = AIMMessage.task("triple", {"n": 7}, sender_id="cli", receiver_id="private-task")
            response = await _send_and_recv("127.0.0.1", 17911, msg)

            assert response is not None
            result = response.payload.get("result", {})
            assert result.get("result") == 21
            assert result.get("status") == "ok"
        finally:
            await client.disconnect()
            await _stop_gateway(gw, gw_task)

    async def test_forwarded_message_logged_in_ledger(self):
        """Each forwarded message produces a ledger entry."""
        ledger = LegacyLedger()
        gw = GatewayNode(host="127.0.0.1", port=17912, ledger=ledger)
        gw_task = await _start_gateway(gw)

        node = AgentNode(node_id="ledger-fwd")
        client = GatewayClient(node, "127.0.0.1", 17912)
        try:
            await client.connect()
            await asyncio.sleep(0.05)

            msg = AIMMessage.query("hello", sender_id="cli", receiver_id="ledger-fwd")
            await _send_and_recv("127.0.0.1", 17912, msg)
            await asyncio.sleep(0.05)

            fwd_entries = ledger.entries_by_kind(_EV_MSG_FORWARDED)
            assert len(fwd_entries) >= 1
            assert fwd_entries[0].payload["target"] == "ledger-fwd"
        finally:
            await client.disconnect()
            await _stop_gateway(gw, gw_task)

    async def test_concurrent_clients_forwarded_correctly(self):
        """Multiple simultaneous public clients get the correct responses."""
        ledger = LegacyLedger()
        gw = GatewayNode(host="127.0.0.1", port=17913, ledger=ledger)
        gw_task = await _start_gateway(gw)

        node = AgentNode(node_id="concurrent-node")

        async def double(args: dict) -> int:
            return args["n"] * 2

        node.register_task("double", double)
        client = GatewayClient(node, "127.0.0.1", 17913)
        try:
            await client.connect()
            await asyncio.sleep(0.05)

            async def send_task(n: int) -> int | None:
                msg = AIMMessage.task(
                    "double", {"n": n}, sender_id="cli", receiver_id="concurrent-node"
                )
                resp = await _send_and_recv("127.0.0.1", 17913, msg)
                if resp is None:
                    return None
                return resp.payload.get("result", {}).get("result")

            results = await asyncio.gather(*[send_task(i) for i in range(1, 6)])
            # Each response should be n*2 for its own n
            assert set(results) == {2, 4, 6, 8, 10}
        finally:
            await client.disconnect()
            await _stop_gateway(gw, gw_task)


# ---------------------------------------------------------------------------
# GatewayClient — unit-level behaviour
# ---------------------------------------------------------------------------

class TestGatewayClient:
    async def test_connect_returns_false_on_bad_host(self):
        """connect() returns False when the gateway is not reachable."""
        node = AgentNode(node_id="no-gw")
        client = GatewayClient(node, "127.0.0.1", 19999, heartbeat_interval=60.0)
        ok = await client.connect(timeout=0.5)
        assert ok is False

    async def test_disconnect_idempotent(self):
        """disconnect() can be called even if not connected."""
        node = AgentNode(node_id="idem-node")
        client = GatewayClient(node, "127.0.0.1", 19998, heartbeat_interval=60.0)
        # Should not raise
        await client.disconnect()

    async def test_context_manager(self):
        """GatewayClient works as an async context manager."""
        ledger = LegacyLedger()
        gw = GatewayNode(host="127.0.0.1", port=17920, ledger=ledger)
        gw_task = await _start_gateway(gw)

        node = AgentNode(node_id="ctx-node")
        try:
            async with GatewayClient(node, "127.0.0.1", 17920) as gc:
                assert gc._connected is True
                assert "ctx-node" in gw.connected_nodes
            # After __aexit__ the client should be disconnected
            assert gc._connected is False
        finally:
            await _stop_gateway(gw, gw_task)


# ---------------------------------------------------------------------------
# Ledger integration
# ---------------------------------------------------------------------------

class TestGatewayLedgerIntegration:
    async def test_disconnect_logged_in_ledger(self):
        """When a private node disconnects, the ledger records the event."""
        from aim.gateway.node import _EV_NODE_DISCONNECTED

        ledger = LegacyLedger()
        gw = GatewayNode(host="127.0.0.1", port=17930, ledger=ledger)
        gw_task = await _start_gateway(gw)

        node = AgentNode(node_id="disc-node")
        client = GatewayClient(node, "127.0.0.1", 17930)
        await client.connect()
        await asyncio.sleep(0.05)
        await client.disconnect()
        # Allow the gateway to process the disconnect
        await asyncio.sleep(0.1)

        disc_entries = ledger.entries_by_kind(_EV_NODE_DISCONNECTED)
        assert any(e.node_id == "disc-node" for e in disc_entries)

        await _stop_gateway(gw, gw_task)

    async def test_full_ledger_audit_trail(self):
        """A complete gateway session produces all expected ledger event types."""
        from aim.gateway.node import _EV_NODE_DISCONNECTED

        ledger = LegacyLedger()
        gw = GatewayNode(host="127.0.0.1", port=17931, ledger=ledger)
        gw_task = await _start_gateway(gw)

        node = AgentNode(node_id="audit-node")
        client = GatewayClient(node, "127.0.0.1", 17931)
        try:
            await client.connect()
            await asyncio.sleep(0.05)

            msg = AIMMessage.query("audit", sender_id="cli", receiver_id="audit-node")
            await _send_and_recv("127.0.0.1", 17931, msg)
            await asyncio.sleep(0.05)
        finally:
            await client.disconnect()
            await asyncio.sleep(0.1)
            await _stop_gateway(gw, gw_task)

        all_kinds = {e.event_kind for e in ledger.all_entries()}
        assert _EV_NODE_REGISTERED in all_kinds
        assert _EV_MSG_FORWARDED in all_kinds
        assert _EV_NODE_DISCONNECTED in all_kinds
