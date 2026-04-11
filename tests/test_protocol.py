"""Tests for the AIM Protocol Layer."""

import json
import pytest

from aim.protocol.message import AIMMessage, Intent, Status
from aim.protocol.handler import ProtocolHandler


# ---------------------------------------------------------------------------
# AIMMessage serialisation
# ---------------------------------------------------------------------------

class TestAIMMessageSerialisation:
    def test_to_json_roundtrip(self):
        msg = AIMMessage.query("hello", sender_id="node-a")
        raw = msg.to_json()
        restored = AIMMessage.from_json(raw)
        assert restored.intent == Intent.QUERY
        assert restored.payload["text"] == "hello"
        assert restored.sender_id == "node-a"
        assert restored.signature == "Cbetts1"

    def test_to_bytes_roundtrip(self):
        msg = AIMMessage.task("summarise", {"doc": "test"}, sender_id="node-b")
        restored = AIMMessage.from_bytes(msg.to_bytes())
        assert restored.intent == Intent.TASK
        assert restored.payload["name"] == "summarise"

    def test_respond_factory(self):
        msg = AIMMessage.query("ping")
        resp = AIMMessage.respond(msg.message_id, result="pong", status=Status.OK)
        assert resp.intent == Intent.RESPOND
        assert resp.correlation_id == msg.message_id
        assert resp.payload["result"] == "pong"
        assert resp.payload["status"] == "ok"

    def test_heartbeat_factory(self):
        hb = AIMMessage.heartbeat(sender_id="x")
        assert hb.intent == Intent.HEARTBEAT
        assert hb.sender_id == "x"

    def test_announce_factory(self):
        ann = AIMMessage.announce(["query", "task"], sender_id="n1")
        assert ann.intent == Intent.ANNOUNCE
        assert "query" in ann.payload["capabilities"]

    def test_default_signature(self):
        msg = AIMMessage(intent=Intent.QUERY, payload={})
        assert msg.signature == "Cbetts1"

    def test_unique_message_ids(self):
        ids = {AIMMessage(intent=Intent.HEARTBEAT).message_id for _ in range(100)}
        assert len(ids) == 100

    def test_ttl_default(self):
        msg = AIMMessage(intent=Intent.QUERY)
        assert msg.ttl == 16


# ---------------------------------------------------------------------------
# ProtocolHandler dispatch
# ---------------------------------------------------------------------------

class TestProtocolHandler:
    @pytest.mark.asyncio
    async def test_dispatch_to_registered_handler(self):
        handler = ProtocolHandler()
        received: list[AIMMessage] = []

        @handler.on(Intent.QUERY)
        async def handle_query(msg: AIMMessage):
            received.append(msg)
            return AIMMessage.respond(msg.message_id, result="answer")

        msg = AIMMessage.query("test question")
        response = await handler.dispatch(msg)
        assert len(received) == 1
        assert response is not None
        assert response.payload["result"] == "answer"

    @pytest.mark.asyncio
    async def test_no_handler_returns_none(self):
        handler = ProtocolHandler()
        msg = AIMMessage.heartbeat()
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
            return AIMMessage.respond(msg.message_id, result="second wins")

        msg = AIMMessage.task("compute")
        response = await handler.dispatch(msg)
        assert response.payload["result"] == "second wins"

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_crash_dispatcher(self):
        handler = ProtocolHandler()

        @handler.on(Intent.QUERY)
        async def bad_handler(msg):
            raise RuntimeError("oops")

        msg = AIMMessage.query("trigger error")
        result = await handler.dispatch(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_register_programmatic(self):
        handler = ProtocolHandler()

        async def fn(msg):
            return AIMMessage.respond(msg.message_id, result="ok")

        handler.register(Intent.HEARTBEAT, fn)
        msg = AIMMessage.heartbeat()
        response = await handler.dispatch(msg)
        assert response.payload["result"] == "ok"
