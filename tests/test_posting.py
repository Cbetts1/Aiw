"""
Tests for the AIM user-facing posting system.

Covers:
  - ContentNode: PUBLISH, READ, LIST via AIMMessage (unit tests)
  - HTTP handler functions: _handle_content_post, _handle_content_list,
    _handle_content_read (integration tests using the real server handlers)
"""

from __future__ import annotations

import json
import pytest

from aim.content.node import ContentNode
from aim.protocol.message import AIMMessage, Intent, Status


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def content_node(tmp_path):
    """An isolated ContentNode backed by a temporary directory."""
    return ContentNode(data_dir=tmp_path)


# ===========================================================================
# ContentNode — direct unit tests
# ===========================================================================


class TestContentNodePublish:
    @pytest.mark.asyncio
    async def test_publish_returns_post(self, content_node):
        msg = AIMMessage.publish(title="Hello", body="World", author="alice")
        resp = await content_node.dispatch(msg)
        result = resp.payload["result"]
        assert result["status"] == "published"
        post = result["post"]
        assert post["title"] == "Hello"
        assert post["body"] == "World"
        assert post["author"] == "alice"
        assert "id" in post
        assert "timestamp" in post

    @pytest.mark.asyncio
    async def test_publish_stores_post(self, content_node):
        msg = AIMMessage.publish(title="Stored", body="Content")
        await content_node.dispatch(msg)
        posts = content_node._load()
        assert len(posts) == 1
        assert posts[0]["title"] == "Stored"

    @pytest.mark.asyncio
    async def test_publish_missing_title_returns_error(self, content_node):
        msg = AIMMessage.publish(title="", body="Some body")
        resp = await content_node.dispatch(msg)
        result = resp.payload["result"]
        assert "error" in result
        assert resp.payload["status"] == Status.ERROR.value

    @pytest.mark.asyncio
    async def test_publish_missing_body_returns_error(self, content_node):
        msg = AIMMessage.publish(title="Title", body="")
        resp = await content_node.dispatch(msg)
        result = resp.payload["result"]
        assert "error" in result

    @pytest.mark.asyncio
    async def test_publish_title_too_long(self, content_node):
        msg = AIMMessage.publish(title="x" * 201, body="body")
        resp = await content_node.dispatch(msg)
        assert "error" in resp.payload["result"]

    @pytest.mark.asyncio
    async def test_publish_body_too_long(self, content_node):
        msg = AIMMessage.publish(title="t", body="x" * 10_001)
        resp = await content_node.dispatch(msg)
        assert "error" in resp.payload["result"]

    @pytest.mark.asyncio
    async def test_publish_anonymous_default(self, content_node):
        msg = AIMMessage.publish(title="T", body="B", author="")
        resp = await content_node.dispatch(msg)
        assert resp.payload["result"]["post"]["author"] == "anonymous"

    @pytest.mark.asyncio
    async def test_publish_multiple_posts(self, content_node):
        for i in range(5):
            await content_node.dispatch(
                AIMMessage.publish(title=f"Post {i}", body=f"Body {i}")
            )
        posts = content_node._load()
        assert len(posts) == 5


class TestContentNodeRead:
    @pytest.mark.asyncio
    async def test_read_existing_post(self, content_node):
        pub = await content_node.dispatch(
            AIMMessage.publish(title="Readable", body="Hello")
        )
        post_id = pub.payload["result"]["post"]["id"]

        msg  = AIMMessage.read_content(content_id=post_id)
        resp = await content_node.dispatch(msg)
        assert resp.payload["result"]["post"]["id"] == post_id
        assert resp.payload["result"]["post"]["title"] == "Readable"

    @pytest.mark.asyncio
    async def test_read_nonexistent_post(self, content_node):
        msg  = AIMMessage.read_content(content_id="does-not-exist")
        resp = await content_node.dispatch(msg)
        assert "error" in resp.payload["result"]
        assert resp.payload["status"] == Status.ERROR.value

    @pytest.mark.asyncio
    async def test_read_missing_id(self, content_node):
        msg  = AIMMessage.read_content(content_id="")
        resp = await content_node.dispatch(msg)
        assert "error" in resp.payload["result"]


class TestContentNodeList:
    @pytest.mark.asyncio
    async def test_list_empty(self, content_node):
        msg  = AIMMessage.list_content()
        resp = await content_node.dispatch(msg)
        result = resp.payload["result"]
        assert result["count"] == 0
        assert result["posts"] == []

    @pytest.mark.asyncio
    async def test_list_returns_newest_first(self, content_node):
        for i in range(3):
            await content_node.dispatch(
                AIMMessage.publish(title=f"Post {i}", body=f"Body {i}")
            )
        msg  = AIMMessage.list_content()
        resp = await content_node.dispatch(msg)
        posts = resp.payload["result"]["posts"]
        assert posts[0]["title"] == "Post 2"
        assert posts[1]["title"] == "Post 1"
        assert posts[2]["title"] == "Post 0"

    @pytest.mark.asyncio
    async def test_list_respects_limit(self, content_node):
        for i in range(10):
            await content_node.dispatch(
                AIMMessage.publish(title=f"P{i}", body="b")
            )
        msg  = AIMMessage.list_content(limit=3)
        resp = await content_node.dispatch(msg)
        assert len(resp.payload["result"]["posts"]) == 3

    @pytest.mark.asyncio
    async def test_list_count_reflects_total(self, content_node):
        for i in range(7):
            await content_node.dispatch(
                AIMMessage.publish(title=f"P{i}", body="b")
            )
        msg  = AIMMessage.list_content(limit=2)
        resp = await content_node.dispatch(msg)
        result = resp.payload["result"]
        assert result["count"] == 7
        assert len(result["posts"]) == 2


class TestContentNodeUnsupportedIntent:
    @pytest.mark.asyncio
    async def test_unsupported_intent_returns_error(self, content_node):
        msg = AIMMessage.heartbeat(sender_id="test")
        resp = await content_node.dispatch(msg)
        assert "error" in resp.payload["result"]


# ===========================================================================
# HTTP handler functions (via the server module)
# ===========================================================================
# We import and call the handler functions directly (no TCP), wiring them to
# an isolated ContentNode via monkeypatching.
# ===========================================================================


@pytest.fixture(autouse=True)
def _patch_content_node(tmp_path, monkeypatch):
    """Replace the server's ContentNode singleton with a fresh isolated one."""
    import aim.web.server as srv
    node = ContentNode(data_dir=tmp_path)
    monkeypatch.setattr(srv, "_content_node", node)


class TestHTTPContentPost:
    @pytest.mark.asyncio
    async def test_post_creates_content(self):
        import aim.web.server as srv
        body = json.dumps({"title": "HTTP Test", "body": "Hello AIM", "author": "bob"}).encode()
        status, resp = await srv._handle_content_post(body)
        assert status == 201
        data = json.loads(resp)
        assert data["status"] == "published"
        assert data["post"]["title"] == "HTTP Test"

    @pytest.mark.asyncio
    async def test_post_invalid_json(self):
        import aim.web.server as srv
        status, resp = await srv._handle_content_post(b"not-json")
        assert status == 400
        assert "error" in json.loads(resp)

    @pytest.mark.asyncio
    async def test_post_missing_title(self):
        import aim.web.server as srv
        body = json.dumps({"title": "", "body": "content"}).encode()
        status, resp = await srv._handle_content_post(body)
        assert status == 400
        assert "error" in json.loads(resp)

    @pytest.mark.asyncio
    async def test_post_missing_body(self):
        import aim.web.server as srv
        body = json.dumps({"title": "Title", "body": ""}).encode()
        status, resp = await srv._handle_content_post(body)
        assert status == 400
        assert "error" in json.loads(resp)


class TestHTTPContentList:
    @pytest.mark.asyncio
    async def test_list_returns_posts(self):
        import aim.web.server as srv
        # Publish two posts first
        for i in range(2):
            await srv._handle_content_post(
                json.dumps({"title": f"Post {i}", "body": f"Body {i}"}).encode()
            )
        status, resp = await srv._handle_content_list({})
        assert status == 200
        data = json.loads(resp)
        assert data["count"] == 2
        assert len(data["posts"]) == 2

    @pytest.mark.asyncio
    async def test_list_empty_store(self):
        import aim.web.server as srv
        status, resp = await srv._handle_content_list({})
        assert status == 200
        data = json.loads(resp)
        assert data["count"] == 0
        assert data["posts"] == []

    @pytest.mark.asyncio
    async def test_list_limit_param(self):
        import aim.web.server as srv
        for i in range(5):
            await srv._handle_content_post(
                json.dumps({"title": f"P{i}", "body": "b"}).encode()
            )
        status, resp = await srv._handle_content_list({"limit": "2"})
        assert status == 200
        data = json.loads(resp)
        assert len(data["posts"]) == 2


class TestHTTPContentRead:
    @pytest.mark.asyncio
    async def test_read_returns_post(self):
        import aim.web.server as srv
        _, pub_resp = await srv._handle_content_post(
            json.dumps({"title": "Readable", "body": "Content"}).encode()
        )
        post_id = json.loads(pub_resp)["post"]["id"]

        status, resp = await srv._handle_content_read(post_id)
        assert status == 200
        data = json.loads(resp)
        assert data["post"]["id"] == post_id
        assert data["post"]["title"] == "Readable"

    @pytest.mark.asyncio
    async def test_read_missing_post(self):
        import aim.web.server as srv
        status, resp = await srv._handle_content_read("nonexistent-id")
        assert status == 404
        assert "error" in json.loads(resp)


# ===========================================================================
# Protocol: new Intent values
# ===========================================================================


class TestIntentValues:
    def test_publish_intent_value(self):
        assert Intent.PUBLISH.value == "publish"

    def test_read_intent_value(self):
        assert Intent.READ.value == "read"

    def test_list_intent_value(self):
        assert Intent.LIST.value == "list"

    def test_publish_factory(self):
        msg = AIMMessage.publish(title="T", body="B", author="x")
        assert msg.intent == Intent.PUBLISH
        assert msg.payload["title"] == "T"
        assert msg.payload["body"] == "B"
        assert msg.payload["author"] == "x"

    def test_read_content_factory(self):
        msg = AIMMessage.read_content(content_id="abc-123")
        assert msg.intent == Intent.READ
        assert msg.payload["id"] == "abc-123"

    def test_list_content_factory(self):
        msg = AIMMessage.list_content(limit=10)
        assert msg.intent == Intent.LIST
        assert msg.payload["limit"] == 10
