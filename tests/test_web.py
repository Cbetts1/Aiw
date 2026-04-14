"""
Tests for the AIM Web Server handler functions.

All handlers are tested directly (without starting a real TCP server), so
these are fast, isolated unit tests.  The ``_isolate_web_data`` fixture
redirects every data file to a temporary directory and resets all module-level
singletons between tests.
"""

from __future__ import annotations

import json
import time
import pytest
from pathlib import Path
from collections import defaultdict


# ---------------------------------------------------------------------------
# Isolation fixture — runs before every test in this module
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_web_data(tmp_path, monkeypatch):
    """Redirect web-server data files to a temp directory and reset singletons."""
    import aim.web.server as srv
    import aim.content.store as cs
    import aim.vcloud.manager as vcm
    import aim.ans.registry as ans
    import aim.ai.brain as brain_mod

    dir_file     = tmp_path / "directory.json"
    posts_file   = tmp_path / "posts.json"
    content_file = tmp_path / "content.jsonl"
    dir_file.write_text("[]")
    posts_file.write_text("[]")

    monkeypatch.setattr(srv, "_DIR_FILE",      dir_file)
    monkeypatch.setattr(srv, "_POSTS_FILE",    posts_file)
    monkeypatch.setattr(srv, "_CONTENT_FILE",  content_file)
    monkeypatch.setattr(srv, "_content_node",  None)
    monkeypatch.setattr(srv, "_rate_buckets",  defaultdict(list))

    # Reset content-store singleton so each test gets a fresh store
    monkeypatch.setattr(cs, "_default_store", None)

    # Reset VCloudManager singleton
    monkeypatch.setattr(vcm.VCloudManager, "_default", None)

    # Reset ANSRegistry singleton
    monkeypatch.setattr(ans.ANSRegistry, "_default", None)

    # Reset AIBrain singleton
    monkeypatch.setattr(brain_mod.AIBrain, "_default", None)

    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json(obj) -> bytes:
    return json.dumps(obj).encode("utf-8")


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimit:
    def test_first_request_allowed(self):
        from aim.web.server import _check_rate_limit
        assert _check_rate_limit("1.2.3.4") is True

    def test_ten_requests_allowed(self):
        from aim.web.server import _check_rate_limit
        for _ in range(10):
            assert _check_rate_limit("10.0.0.1") is True

    def test_eleventh_request_rejected(self):
        from aim.web.server import _check_rate_limit
        for _ in range(10):
            _check_rate_limit("10.0.0.2")
        assert _check_rate_limit("10.0.0.2") is False

    def test_separate_ips_are_independent(self):
        from aim.web.server import _check_rate_limit
        for _ in range(10):
            _check_rate_limit("10.0.0.3")
        # Different IP is unaffected
        assert _check_rate_limit("10.0.0.4") is True

    def test_expired_entries_pruned(self, monkeypatch):
        """Timestamps older than the window should be discarded."""
        import aim.web.server as srv
        from aim.web.server import _check_rate_limit, _RATE_WINDOW_SECONDS

        ip = "192.168.1.1"
        # Pre-fill with old timestamps
        old_ts = time.time() - _RATE_WINDOW_SECONDS - 1
        srv._rate_buckets[ip] = [old_ts] * 10
        # Now a new request must be allowed because old entries are pruned
        assert _check_rate_limit(ip) is True


# ---------------------------------------------------------------------------
# /api/info
# ---------------------------------------------------------------------------

class TestHandleInfo:
    def test_returns_200_with_name_and_version(self):
        from aim.web.server import _handle_info
        status, body = _handle_info()
        assert status == 200
        data = json.loads(body)
        assert data["name"] == "AIM Web Bridge"
        assert "version" in data
        assert "origin" in data


# ---------------------------------------------------------------------------
# Directory API
# ---------------------------------------------------------------------------

class TestDirectoryHandlers:
    def test_get_empty_directory(self):
        from aim.web.server import _handle_directory_get
        status, body = _handle_directory_get()
        assert status == 200
        data = json.loads(body)
        assert data["count"] == 0
        assert data["entries"] == []

    def test_post_adds_entry(self):
        from aim.web.server import _handle_directory_post, _handle_directory_get
        payload = _json({
            "name": "My Tool",
            "url": "https://example.com",
            "description": "A useful tool",
            "category": "tool",
        })
        status, body = _handle_directory_post(payload)
        assert status == 201
        data = json.loads(body)
        assert data["status"] == "added"
        assert data["entry"]["name"] == "My Tool"
        assert data["entry"]["url"] == "https://example.com"

        # Verify it's now in the directory
        status2, body2 = _handle_directory_get()
        data2 = json.loads(body2)
        assert data2["count"] == 1

    def test_post_requires_name(self):
        from aim.web.server import _handle_directory_post
        payload = _json({"url": "https://example.com"})
        status, body = _handle_directory_post(payload)
        assert status == 400
        assert "name is required" in json.loads(body)["error"]

    def test_post_requires_url(self):
        from aim.web.server import _handle_directory_post
        payload = _json({"name": "My Tool"})
        status, body = _handle_directory_post(payload)
        assert status == 400
        assert "url is required" in json.loads(body)["error"]

    def test_post_requires_https_url(self):
        from aim.web.server import _handle_directory_post
        payload = _json({"name": "My Tool", "url": "ftp://example.com"})
        status, body = _handle_directory_post(payload)
        assert status == 400
        assert "http" in json.loads(body)["error"]

    def test_post_invalid_json(self):
        from aim.web.server import _handle_directory_post
        status, body = _handle_directory_post(b"not-json")
        assert status == 400

    def test_post_name_too_long(self):
        from aim.web.server import _handle_directory_post
        payload = _json({"name": "x" * 121, "url": "https://example.com"})
        status, body = _handle_directory_post(payload)
        assert status == 400

    def test_post_description_too_long(self):
        from aim.web.server import _handle_directory_post
        payload = _json({
            "name": "Tool",
            "url": "https://example.com",
            "description": "x" * 501,
        })
        status, body = _handle_directory_post(payload)
        assert status == 400

    def test_invalid_category_defaults_to_other(self):
        from aim.web.server import _handle_directory_post
        payload = _json({
            "name": "Tool",
            "url": "https://example.com",
            "category": "nonsense",
        })
        status, body = _handle_directory_post(payload)
        assert status == 201
        assert json.loads(body)["entry"]["category"] == "other"

    def test_multiple_entries_accumulate(self):
        from aim.web.server import _handle_directory_post, _handle_directory_get
        for i in range(3):
            _handle_directory_post(_json({
                "name": f"Tool {i}",
                "url": f"https://example{i}.com",
            }))
        status, body = _handle_directory_get()
        assert json.loads(body)["count"] == 3


# ---------------------------------------------------------------------------
# Posts API
# ---------------------------------------------------------------------------

class TestPostsHandlers:
    def test_get_empty_posts(self):
        from aim.web.server import _handle_posts_get
        status, body = _handle_posts_get({})
        assert status == 200
        data = json.loads(body)
        assert data["count"] == 0
        assert data["posts"] == []

    def test_post_adds_entry(self):
        from aim.web.server import _handle_posts_post, _handle_posts_get
        payload = _json({"author": "alice", "message": "Hello AIM!"})
        status, body = _handle_posts_post(payload)
        assert status == 201
        data = json.loads(body)
        assert data["status"] == "posted"
        assert data["post"]["author"] == "alice"
        assert data["post"]["message"] == "Hello AIM!"
        assert "id" in data["post"]
        assert "timestamp" in data["post"]

        # Verify it appears in the list
        status2, body2 = _handle_posts_get({})
        data2 = json.loads(body2)
        assert data2["count"] == 1

    def test_post_requires_message(self):
        from aim.web.server import _handle_posts_post
        payload = _json({"author": "alice"})
        status, body = _handle_posts_post(payload)
        assert status == 400
        assert "message is required" in json.loads(body)["error"]

    def test_post_message_too_long(self):
        from aim.web.server import _handle_posts_post
        payload = _json({"message": "x" * 1001})
        status, body = _handle_posts_post(payload)
        assert status == 400

    def test_post_defaults_author_to_anonymous(self):
        from aim.web.server import _handle_posts_post
        payload = _json({"message": "Hi"})
        status, body = _handle_posts_post(payload)
        assert status == 201
        assert json.loads(body)["post"]["author"] == "anonymous"

    def test_get_posts_newest_first(self):
        from aim.web.server import _handle_posts_post, _handle_posts_get
        _handle_posts_post(_json({"message": "First post"}))
        _handle_posts_post(_json({"message": "Second post"}))
        status, body = _handle_posts_get({})
        posts = json.loads(body)["posts"]
        assert posts[0]["message"] == "Second post"
        assert posts[1]["message"] == "First post"

    def test_get_posts_limit(self):
        from aim.web.server import _handle_posts_post, _handle_posts_get
        for i in range(5):
            _handle_posts_post(_json({"message": f"Post {i}"}))
        status, body = _handle_posts_get({"limit": "3"})
        assert len(json.loads(body)["posts"]) == 3

    def test_post_invalid_json(self):
        from aim.web.server import _handle_posts_post
        status, body = _handle_posts_post(b"not-json")
        assert status == 400


# ---------------------------------------------------------------------------
# Content API
# ---------------------------------------------------------------------------

class TestContentHandlers:
    def test_post_publishes_item(self):
        from aim.web.server import _handle_content_post_direct
        payload = _json({
            "body": "Hello, content layer!",
            "author": "bob",
            "title": "Test Post",
        })
        status, body = _handle_content_post_direct(payload)
        assert status == 201
        data = json.loads(body)
        assert data["status"] == "published"
        assert data["item"]["body"] == "Hello, content layer!"
        assert data["item"]["author"] == "bob"

    def test_post_requires_body(self):
        from aim.web.server import _handle_content_post_direct
        payload = _json({"author": "bob"})
        status, body = _handle_content_post_direct(payload)
        assert status == 400

    def test_post_invalid_json(self):
        from aim.web.server import _handle_content_post_direct
        status, body = _handle_content_post_direct(b"not-json")
        assert status == 400

    def test_get_by_id_returns_item(self):
        from aim.web.server import _handle_content_post_direct, _handle_content_get_by_id
        pub_status, pub_body = _handle_content_post_direct(_json({
            "body": "Retrievable content",
            "author": "alice",
        }))
        assert pub_status == 201
        content_id = json.loads(pub_body)["item"]["id"]

        status, body = _handle_content_get_by_id(content_id)
        assert status == 200
        data = json.loads(body)
        assert data["item"]["body"] == "Retrievable content"

    def test_get_by_id_missing_returns_404(self):
        from aim.web.server import _handle_content_get_by_id
        status, body = _handle_content_get_by_id("no-such-id")
        assert status == 404

    def test_list_returns_items(self):
        from aim.web.server import _handle_content_post_direct, _handle_content_list_direct
        _handle_content_post_direct(_json({"body": "Item A"}))
        _handle_content_post_direct(_json({"body": "Item B"}))
        status, body = _handle_content_list_direct({})
        assert status == 200
        data = json.loads(body)
        assert data["count"] == 2
        assert len(data["items"]) == 2

    def test_list_filter_by_author(self):
        from aim.web.server import _handle_content_post_direct, _handle_content_list_direct
        _handle_content_post_direct(_json({"body": "By Alice", "author": "alice"}))
        _handle_content_post_direct(_json({"body": "By Bob",   "author": "bob"}))
        status, body = _handle_content_list_direct({"author": "alice"})
        data = json.loads(body)
        assert data["count"] == 1
        assert data["items"][0]["author"] == "alice"

    def test_list_limit_and_offset(self):
        from aim.web.server import _handle_content_post_direct, _handle_content_list_direct
        for i in range(6):
            _handle_content_post_direct(_json({"body": f"Item {i}"}))
        status, body = _handle_content_list_direct({"limit": "3", "offset": "0"})
        data = json.loads(body)
        assert len(data["items"]) == 3


# ---------------------------------------------------------------------------
# ANS API
# ---------------------------------------------------------------------------

class TestAnsHandlers:
    def test_get_missing_name_returns_400(self):
        from aim.web.server import _handle_ans_get
        status, body = _handle_ans_get({})
        assert status == 400

    def test_get_unknown_name_returns_404(self):
        from aim.web.server import _handle_ans_get
        status, body = _handle_ans_get({"name": "no-such-node"})
        assert status == 404

    def test_get_registered_name_returns_200(self):
        from aim.web.server import _handle_ans_get
        from aim.ans.registry import ANSRegistry, ANSRecord
        registry = ANSRegistry.default()
        registry.register(ANSRecord(
            name="mynode.aim",
            node_id="test-node-001",
            host="127.0.0.1",
            port=7700,
            capabilities=["query"],
        ))
        status, body = _handle_ans_get({"name": "mynode.aim"})
        assert status == 200
        data = json.loads(body)
        assert data["name"] == "mynode.aim"
        assert data["node_id"] == "test-node-001"


# ---------------------------------------------------------------------------
# VCloud API
# ---------------------------------------------------------------------------

class TestVCloudHandlers:
    def test_get_empty_returns_200(self):
        from aim.web.server import _handle_vcloud_get
        status, body = _handle_vcloud_get()
        assert status == 200
        data = json.loads(body)
        assert "resources" in data or isinstance(data, dict)

    def test_post_vcpu_creates_resource(self):
        from aim.web.server import _handle_vcloud_post, _handle_vcloud_get
        payload = _json({"kind": "vcpu", "name": "test-cpu", "cores": 2})
        status, body = _handle_vcloud_post(payload)
        assert status == 201
        data = json.loads(body)
        assert data["status"] == "created"
        assert data["resource"]["name"] == "test-cpu"

    def test_post_vserver_creates_resource(self):
        from aim.web.server import _handle_vcloud_post
        payload = _json({
            "kind": "vserver",
            "name": "test-server",
            "memory_mb": 1024,
        })
        status, body = _handle_vcloud_post(payload)
        assert status == 201
        data = json.loads(body)
        assert data["resource"]["name"] == "test-server"

    def test_post_vcloud_creates_resource(self):
        from aim.web.server import _handle_vcloud_post
        payload = _json({"kind": "vcloud", "name": "test-cloud"})
        status, body = _handle_vcloud_post(payload)
        assert status == 201

    def test_post_unknown_kind_returns_400(self):
        from aim.web.server import _handle_vcloud_post
        payload = _json({"kind": "hyperdrive", "name": "x"})
        status, body = _handle_vcloud_post(payload)
        assert status == 400

    def test_post_invalid_json_returns_400(self):
        from aim.web.server import _handle_vcloud_post
        status, body = _handle_vcloud_post(b"not-json")
        assert status == 400

    def test_delete_removes_resource(self):
        from aim.web.server import _handle_vcloud_post, _handle_vcloud_delete
        _, create_body = _handle_vcloud_post(_json({"kind": "vcpu", "name": "del-me"}))
        resource_id = json.loads(create_body)["resource"]["resource_id"]

        status, body = _handle_vcloud_delete({"id": resource_id})
        assert status == 200
        assert json.loads(body)["status"] == "destroyed"

    def test_delete_missing_id_returns_400(self):
        from aim.web.server import _handle_vcloud_delete
        status, body = _handle_vcloud_delete({})
        assert status == 400

    def test_delete_nonexistent_id_returns_404(self):
        from aim.web.server import _handle_vcloud_delete
        status, body = _handle_vcloud_delete({"id": "no-such-resource"})
        assert status == 404


# ---------------------------------------------------------------------------
# DNS bridge API
# ---------------------------------------------------------------------------

class TestDnsHandlers:
    def test_resolve_missing_name_returns_400(self):
        from aim.web.server import _handle_dns_resolve
        status, body = _handle_dns_resolve({})
        assert status == 400

    def test_records_returns_list(self):
        from aim.web.server import _handle_dns_records
        status, body = _handle_dns_records()
        assert status == 200
        data = json.loads(body)
        assert "count" in data
        assert "records" in data

    def test_register_creates_record(self):
        from aim.web.server import _handle_dns_register, _handle_dns_records
        payload = _json({
            "hostname": "myserver.local",
            "port": 7700,
            "capabilities": ["query"],
        })
        status, body = _handle_dns_register(payload)
        assert status == 201
        data = json.loads(body)
        assert data["status"] == "registered"
        assert data["port"] == 7700

        # Record should now appear in the list
        _, list_body = _handle_dns_records()
        list_data = json.loads(list_body)
        assert list_data["count"] >= 1

    def test_register_missing_hostname_returns_400(self):
        from aim.web.server import _handle_dns_register
        payload = _json({"port": 7700})
        status, body = _handle_dns_register(payload)
        assert status == 400

    def test_register_missing_port_returns_400(self):
        from aim.web.server import _handle_dns_register
        payload = _json({"hostname": "myserver.local"})
        status, body = _handle_dns_register(payload)
        assert status == 400

    def test_register_invalid_json_returns_400(self):
        from aim.web.server import _handle_dns_register
        status, body = _handle_dns_register(b"not-json")
        assert status == 400


# ---------------------------------------------------------------------------
# AI Brain API
# ---------------------------------------------------------------------------

class TestAiBrainHandlers:
    @pytest.mark.asyncio
    async def test_ai_query_get_known_topic(self):
        from aim.web.server import _handle_ai_query
        status, body = await _handle_ai_query({"q": "what is aim"}, b"", "GET")
        assert status == 200
        data = json.loads(body)
        assert "answer" in data
        assert data["answer"]  # non-empty

    @pytest.mark.asyncio
    async def test_ai_query_post_known_topic(self):
        from aim.web.server import _handle_ai_query
        payload = _json({"query": "what is the mesh"})
        status, body = await _handle_ai_query({}, payload, "POST")
        assert status == 200
        data = json.loads(body)
        assert "answer" in data

    @pytest.mark.asyncio
    async def test_ai_query_missing_text_returns_400(self):
        from aim.web.server import _handle_ai_query
        status, body = await _handle_ai_query({}, b"", "GET")
        assert status == 400

    @pytest.mark.asyncio
    async def test_ai_query_post_invalid_json_returns_400(self):
        from aim.web.server import _handle_ai_query
        status, body = await _handle_ai_query({}, b"not-json", "POST")
        assert status == 400

    def test_ai_status_returns_200(self):
        from aim.web.server import _handle_ai_status
        status, body = _handle_ai_status()
        assert status == 200
        data = json.loads(body)
        assert isinstance(data, dict)

    def test_ai_session_history_missing_id_returns_400(self):
        from aim.web.server import _handle_ai_session_history
        status, body = _handle_ai_session_history({})
        assert status == 400

    def test_ai_session_history_new_session_empty(self):
        from aim.web.server import _handle_ai_session_history
        status, body = _handle_ai_session_history({"session_id": "brand-new-session"})
        assert status == 200
        data = json.loads(body)
        assert data["session_id"] == "brand-new-session"
        assert data["history"] == []


# ---------------------------------------------------------------------------
# Remote Connections API
# ---------------------------------------------------------------------------

class TestConnectionsHandlers:
    def test_get_empty_returns_200(self):
        from aim.web.server import _handle_connections_get
        status, body = _handle_connections_get()
        assert status == 200
        data = json.loads(body)
        assert data["count"] == 0

    def test_post_adds_connection(self):
        from aim.web.server import _handle_connections_post, _handle_connections_get
        payload = _json({"name": "My Node", "host": "127.0.0.1", "port": 7700})
        status, body = _handle_connections_post(payload)
        assert status == 201
        data = json.loads(body)
        assert data["status"] == "connected"
        assert "connection" in data

        # Should now appear in the list
        status2, body2 = _handle_connections_get()
        assert json.loads(body2)["count"] == 1

    def test_post_missing_host_returns_400(self):
        from aim.web.server import _handle_connections_post
        payload = _json({"port": 7700})
        status, body = _handle_connections_post(payload)
        assert status == 400

    def test_post_missing_port_returns_400(self):
        from aim.web.server import _handle_connections_post
        payload = _json({"host": "127.0.0.1"})
        status, body = _handle_connections_post(payload)
        assert status == 400

    def test_post_invalid_json_returns_400(self):
        from aim.web.server import _handle_connections_post
        status, body = _handle_connections_post(b"not-json")
        assert status == 400

    def test_delete_removes_connection(self):
        from aim.web.server import _handle_connections_post, _handle_connections_delete
        _, create_body = _handle_connections_post(
            _json({"name": "Deletable", "host": "10.0.0.1", "port": 7800})
        )
        conn_id = json.loads(create_body)["connection"]["resource_id"]
        status, body = _handle_connections_delete({"id": conn_id})
        assert status == 200
        assert json.loads(body)["status"] == "disconnected"

    def test_delete_missing_id_returns_400(self):
        from aim.web.server import _handle_connections_delete
        status, body = _handle_connections_delete({})
        assert status == 400

    def test_delete_nonexistent_returns_404(self):
        from aim.web.server import _handle_connections_delete
        status, body = _handle_connections_delete({"id": "no-such-conn"})
        assert status == 404
