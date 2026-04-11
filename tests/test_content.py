"""
Tests for the AIM Content Layer.

Covers:
- ContentItem schema and serialisation
- ContentStore.publish / read / list
- ContentNode handling PUBLISH, READ, LIST intents via AIMMessage
- Protocol: new Intent values (PUBLISH, READ, LIST)
"""

from __future__ import annotations

import pytest

from aim.protocol.message import AIMMessage, Intent, Status
from aim.content.store import ContentItem, ContentStore
from aim.content.node import ContentNode


# ---------------------------------------------------------------------------
# Intent enum
# ---------------------------------------------------------------------------

class TestContentIntents:
    def test_publish_intent_exists(self):
        assert Intent.PUBLISH == "publish"

    def test_read_intent_exists(self):
        assert Intent.READ == "read"

    def test_list_intent_exists(self):
        assert Intent.LIST == "list"

    def test_intents_serialise_in_message(self):
        msg = AIMMessage(intent=Intent.PUBLISH, payload={"body": "hello"})
        raw = msg.to_json()
        restored = AIMMessage.from_json(raw)
        assert restored.intent == Intent.PUBLISH


# ---------------------------------------------------------------------------
# ContentItem
# ---------------------------------------------------------------------------

class TestContentItem:
    def test_defaults(self):
        item = ContentItem(body="Hello world")
        assert item.body == "Hello world"
        assert item.visibility == "public"
        assert item.content_type == "post"
        assert item.id  # non-empty UUID
        assert item.timestamp > 0

    def test_to_dict_roundtrip(self):
        item = ContentItem(
            body="Test",
            author="alice",
            title="My Post",
            tags=["aim", "test"],
        )
        d = item.to_dict()
        restored = ContentItem.from_dict(d)
        assert restored.body == "Test"
        assert restored.author == "alice"
        assert restored.title == "My Post"
        assert restored.tags == ["aim", "test"]
        assert restored.id == item.id

    def test_from_dict_ignores_unknown_fields(self):
        d = ContentItem(body="hi").to_dict()
        d["unknown_field"] = "should be ignored"
        item = ContentItem.from_dict(d)  # must not raise
        assert item.body == "hi"


# ---------------------------------------------------------------------------
# ContentStore
# ---------------------------------------------------------------------------

class TestContentStore:
    def _fresh_store(self) -> ContentStore:
        return ContentStore()  # in-memory only

    def test_publish_returns_item(self):
        store = self._fresh_store()
        item = store.publish(body="Hello AIM")
        assert item.id
        assert item.body == "Hello AIM"

    def test_publish_validates_empty_body(self):
        store = self._fresh_store()
        with pytest.raises(ValueError, match="body must not be empty"):
            store.publish(body="   ")

    def test_publish_validates_body_too_large(self):
        store = self._fresh_store()
        big = "x" * (65_536 + 1)
        with pytest.raises(ValueError, match="body exceeds"):
            store.publish(body=big)

    def test_read_returns_item(self):
        store = self._fresh_store()
        item = store.publish(body="Readable content")
        result = store.read(item.id)
        assert result is not None
        assert result.id == item.id
        assert result.body == "Readable content"

    def test_read_missing_returns_none(self):
        store = self._fresh_store()
        assert store.read("nonexistent-id") is None

    def test_list_returns_all(self):
        store = self._fresh_store()
        store.publish(body="Post A")
        store.publish(body="Post B")
        store.publish(body="Post C")
        items = store.list()
        assert len(items) == 3

    def test_list_newest_first(self):
        store = self._fresh_store()
        a = store.publish(body="First")
        b = store.publish(body="Second")
        items = store.list()
        assert items[0].id == b.id
        assert items[1].id == a.id

    def test_list_filter_by_author(self):
        store = self._fresh_store()
        store.publish(body="By Alice", author="alice")
        store.publish(body="By Bob", author="bob")
        items = store.list(author="alice")
        assert len(items) == 1
        assert items[0].author == "alice"

    def test_list_filter_by_tag(self):
        store = self._fresh_store()
        store.publish(body="Tagged AIM", tags=["aim", "network"])
        store.publish(body="Untagged")
        items = store.list(tag="aim")
        assert len(items) == 1
        assert "aim" in items[0].tags

    def test_list_filter_by_visibility(self):
        store = self._fresh_store()
        store.publish(body="Public post", visibility="public")
        store.publish(body="Private post", visibility="private")
        public = store.list(visibility="public")
        private = store.list(visibility="private")
        assert len(public) == 1
        assert len(private) == 1

    def test_list_filter_by_content_type(self):
        store = self._fresh_store()
        store.publish(body="A note", content_type="note")
        store.publish(body="A post", content_type="post")
        notes = store.list(content_type="note")
        assert len(notes) == 1
        assert notes[0].content_type == "note"

    def test_list_limit_and_offset(self):
        store = self._fresh_store()
        for i in range(10):
            store.publish(body=f"Post {i}")
        page1 = store.list(limit=3, offset=0)
        page2 = store.list(limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 3
        # No overlap
        ids1 = {i.id for i in page1}
        ids2 = {i.id for i in page2}
        assert ids1.isdisjoint(ids2)

    def test_count(self):
        store = self._fresh_store()
        assert store.count() == 0
        store.publish(body="one")
        store.publish(body="two")
        assert store.count() == 2

    def test_tags_truncated(self):
        store = self._fresh_store()
        item = store.publish(body="Tagged", tags=["a"] * 25)
        assert len(item.tags) == 20  # capped at MAX_TAGS

    def test_invalid_visibility_defaults_to_public(self):
        store = self._fresh_store()
        item = store.publish(body="Content", visibility="secret")
        assert item.visibility == "public"

    def test_author_sig_stored(self):
        store = self._fresh_store()
        item = store.publish(body="Signed", author_sig="test-digest-abc123")
        assert item.signature == "test-digest-abc123"

    def test_persist_and_reload(self, tmp_path):
        path = str(tmp_path / "content.jsonl")
        store1 = ContentStore(persist_path=path)
        a = store1.publish(body="Persistent A")
        b = store1.publish(body="Persistent B")

        store2 = ContentStore(persist_path=path)
        assert store2.count() == 2
        assert store2.read(a.id) is not None
        assert store2.read(b.id).body == "Persistent B"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# ContentNode — AIM intent handling
# ---------------------------------------------------------------------------

class TestContentNode:
    def _node(self) -> ContentNode:
        return ContentNode(node_id="test-content-node", store=ContentStore())

    @pytest.mark.asyncio
    async def test_publish_intent(self):
        node = self._node()
        msg = AIMMessage(
            intent=Intent.PUBLISH,
            payload={"body": "Hello from AIM", "author": "alice", "tags": ["aim"]},
            sender_id="client-1",
        )
        response = await node._handler.dispatch(msg)
        assert response is not None
        assert response.payload["result"]["status"] == "published"
        item = response.payload["result"]["item"]
        assert item["body"] == "Hello from AIM"
        assert item["author"] == "alice"
        assert "aim" in item["tags"]

    @pytest.mark.asyncio
    async def test_publish_invalid_body_returns_error(self):
        node = self._node()
        msg = AIMMessage(
            intent=Intent.PUBLISH,
            payload={"body": ""},
            sender_id="client-1",
        )
        response = await node._handler.dispatch(msg)
        assert response is not None
        assert response.payload["status"] == Status.ERROR.value
        assert "error" in response.payload["result"]

    @pytest.mark.asyncio
    async def test_read_intent(self):
        node = self._node()
        # First publish
        item = node._content_store.publish(body="Readable via intent")
        # Then read
        msg = AIMMessage(
            intent=Intent.READ,
            payload={"id": item.id},
            sender_id="client-1",
        )
        response = await node._handler.dispatch(msg)
        assert response is not None
        result = response.payload["result"]
        assert result["item"]["id"] == item.id
        assert result["item"]["body"] == "Readable via intent"

    @pytest.mark.asyncio
    async def test_read_missing_id(self):
        node = self._node()
        msg = AIMMessage(
            intent=Intent.READ,
            payload={},
            sender_id="client-1",
        )
        response = await node._handler.dispatch(msg)
        assert response is not None
        assert response.payload["status"] == Status.ERROR.value

    @pytest.mark.asyncio
    async def test_read_nonexistent_id(self):
        node = self._node()
        msg = AIMMessage(
            intent=Intent.READ,
            payload={"id": "no-such-id"},
            sender_id="client-1",
        )
        response = await node._handler.dispatch(msg)
        assert response is not None
        assert response.payload["status"] == Status.ERROR.value

    @pytest.mark.asyncio
    async def test_list_intent_all(self):
        node = self._node()
        node._content_store.publish(body="Item 1")
        node._content_store.publish(body="Item 2")
        msg = AIMMessage(
            intent=Intent.LIST,
            payload={},
            sender_id="client-1",
        )
        response = await node._handler.dispatch(msg)
        assert response is not None
        result = response.payload["result"]
        assert result["count"] == 2
        assert len(result["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_intent_with_filter(self):
        node = self._node()
        node._content_store.publish(body="Note", content_type="note")
        node._content_store.publish(body="Post", content_type="post")
        msg = AIMMessage(
            intent=Intent.LIST,
            payload={"content_type": "note"},
            sender_id="client-1",
        )
        response = await node._handler.dispatch(msg)
        assert response is not None
        result = response.payload["result"]
        assert result["count"] == 1
        assert result["items"][0]["content_type"] == "note"

    @pytest.mark.asyncio
    async def test_publish_then_read_roundtrip(self):
        node = self._node()
        # Publish via intent
        pub_msg = AIMMessage(
            intent=Intent.PUBLISH,
            payload={
                "body": "Intent roundtrip",
                "author": "tester",
                "tags": ["roundtrip"],
                "visibility": "public",
            },
            sender_id="client-1",
        )
        pub_response = await node._handler.dispatch(pub_msg)
        assert pub_response is not None
        content_id = pub_response.payload["result"]["item"]["id"]

        # Read back via intent
        read_msg = AIMMessage(
            intent=Intent.READ,
            payload={"id": content_id},
            sender_id="client-1",
        )
        read_response = await node._handler.dispatch(read_msg)
        assert read_response is not None
        assert read_response.payload["result"]["item"]["body"] == "Intent roundtrip"

    @pytest.mark.asyncio
    async def test_inherited_heartbeat_still_works(self):
        """ContentNode must not break inherited BaseNode handlers."""
        node = self._node()
        hb = AIMMessage.heartbeat(sender_id="client-1")
        response = await node._handler.dispatch(hb)
        assert response is not None
        assert response.payload["result"]["alive"] is True
