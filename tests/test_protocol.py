"""Tests for the Meshara Protocol Layer."""

import json
import pytest

from meshara.protocol.message import MesharaMessage, Intent, Status
from meshara.protocol.handler import ProtocolHandler


# ---------------------------------------------------------------------------
# MesharaMessage serialisation
# ---------------------------------------------------------------------------

class TestAIMMessageSerialisation:
    def test_to_json_roundtrip(self):
        msg = MesharaMessage.query("hello", sender_id="node-a")
        raw = msg.to_json()
        restored = MesharaMessage.from_json(raw)
        assert restored.intent == Intent.QUERY
        assert restored.payload["text"] == "hello"
        assert restored.sender_id == "node-a"
        assert restored.signature == "Cbetts1"

    def test_to_bytes_roundtrip(self):
        msg = MesharaMessage.task("summarise", {"doc": "test"}, sender_id="node-b")
        restored = MesharaMessage.from_bytes(msg.to_bytes())
        assert restored.intent == Intent.TASK
        assert restored.payload["name"] == "summarise"

    def test_respond_factory(self):
        msg = MesharaMessage.query("ping")
        resp = MesharaMessage.respond(msg.message_id, result="pong", status=Status.OK)
        assert resp.intent == Intent.RESPOND
        assert resp.correlation_id == msg.message_id
        assert resp.payload["result"] == "pong"
        assert resp.payload["status"] == "ok"

    def test_heartbeat_factory(self):
        hb = MesharaMessage.heartbeat(sender_id="x")
        assert hb.intent == Intent.HEARTBEAT
        assert hb.sender_id == "x"

    def test_announce_factory(self):
        ann = MesharaMessage.announce(["query", "task"], sender_id="n1")
        assert ann.intent == Intent.ANNOUNCE
        assert "query" in ann.payload["capabilities"]

    def test_default_signature(self):
        msg = MesharaMessage(intent=Intent.QUERY, payload={})
        assert msg.signature == "Cbetts1"

    def test_unique_message_ids(self):
        ids = {MesharaMessage(intent=Intent.HEARTBEAT).message_id for _ in range(100)}
        assert len(ids) == 100

    def test_ttl_default(self):
        msg = MesharaMessage(intent=Intent.QUERY)
        assert msg.ttl == 16


# ---------------------------------------------------------------------------
# ProtocolHandler dispatch
# ---------------------------------------------------------------------------

class TestProtocolHandler:
    @pytest.mark.asyncio
    async def test_dispatch_to_registered_handler(self):
        handler = ProtocolHandler()
        received: list[MesharaMessage] = []

        @handler.on(Intent.QUERY)
        async def handle_query(msg: MesharaMessage):
            received.append(msg)
            return MesharaMessage.respond(msg.message_id, result="answer")

        msg = MesharaMessage.query("test question")
        response = await handler.dispatch(msg)
        assert len(received) == 1
        assert response is not None
        assert response.payload["result"] == "answer"

    @pytest.mark.asyncio
    async def test_no_handler_returns_none(self):
        handler = ProtocolHandler()
        msg = MesharaMessage.heartbeat()
        result = await handler.dispatch(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_first_non_none_response_wins(self):
        handler = ProtocolHandler()

        @handler.on(Intent.TASK)
        async def first(msg):
            return None  # pass through

        @handler.on(Intent.TASK)
        async def second(msg):
            return MesharaMessage.respond(msg.message_id, result="second wins")

        msg = MesharaMessage.task("compute")
        response = await handler.dispatch(msg)
        assert response.payload["result"] == "second wins"

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_crash_dispatcher(self):
        handler = ProtocolHandler()

        @handler.on(Intent.QUERY)
        async def bad_handler(msg):
            raise RuntimeError("oops")

        msg = MesharaMessage.query("trigger error")
        result = await handler.dispatch(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_register_programmatic(self):
        handler = ProtocolHandler()

        async def fn(msg):
            return MesharaMessage.respond(msg.message_id, result="ok")

        handler.register(Intent.HEARTBEAT, fn)
        msg = MesharaMessage.heartbeat()
        response = await handler.dispatch(msg)
        assert response.payload["result"] == "ok"
