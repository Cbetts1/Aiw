"""
Tests for aim.content.ContentLayer and ContentItem.
"""

from __future__ import annotations

import time
import pytest

from aim.content.layer import ContentLayer, ContentItem
from aim.identity.ledger import LegacyLedger
from aim.identity.signature import CreatorSignature


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_layer() -> ContentLayer:
    return ContentLayer(ledger=LegacyLedger())


# ---------------------------------------------------------------------------
# ContentItem tests
# ---------------------------------------------------------------------------

class TestContentItem:
    def test_default_fields(self):
        item = ContentItem(body="hello")
        assert item.content_type == "text"
        assert not item.deleted
        assert item.content_id  # non-empty UUID

    def test_to_dict_and_from_dict(self):
        item = ContentItem(body="world", content_type="json")
        d = item.to_dict()
        restored = ContentItem.from_dict(d)
        assert restored.content_id == item.content_id
        assert restored.body == "world"
        assert restored.content_type == "json"


# ---------------------------------------------------------------------------
# ContentLayer.post tests
# ---------------------------------------------------------------------------

class TestContentLayerPost:
    def test_post_returns_content_item(self):
        layer = _make_layer()
        item = layer.post("Hello, mesh!")
        assert isinstance(item, ContentItem)
        assert item.body == "Hello, mesh!"

    def test_post_auto_generates_id(self):
        layer = _make_layer()
        a = layer.post("a")
        b = layer.post("b")
        assert a.content_id != b.content_id

    def test_post_stores_author_from_sig(self):
        layer = _make_layer()
        sig = CreatorSignature()
        item = layer.post("signed", author_sig=sig)
        assert item.author == sig.creator
        assert item.signature_digest == sig.digest

    def test_post_without_sig_uses_origin_creator(self):
        from aim.identity.signature import ORIGIN_CREATOR
        layer = _make_layer()
        item = layer.post("unsigned")
        assert item.author == ORIGIN_CREATOR

    def test_post_records_ledger_event(self):
        ledger = LegacyLedger()
        layer = ContentLayer(ledger=ledger)
        layer.post("track me")
        kinds = [e.event_kind for e in ledger.all_entries()]
        assert "content_posted" in kinds

    def test_count_increases_after_post(self):
        layer = _make_layer()
        assert layer.count() == 0
        layer.post("one")
        layer.post("two")
        assert layer.count() == 2


# ---------------------------------------------------------------------------
# ContentLayer.get tests
# ---------------------------------------------------------------------------

class TestContentLayerGet:
    def test_get_returns_posted_item(self):
        layer = _make_layer()
        item = layer.post("retrieve me")
        fetched = layer.get(item.content_id)
        assert fetched is not None
        assert fetched.body == "retrieve me"

    def test_get_missing_returns_none(self):
        layer = _make_layer()
        assert layer.get("does-not-exist") is None

    def test_get_deleted_returns_none(self):
        layer = _make_layer()
        sig = CreatorSignature()
        item = layer.post("to be deleted", author_sig=sig)
        layer.delete(item.content_id, requester_sig=sig)
        assert layer.get(item.content_id) is None


# ---------------------------------------------------------------------------
# ContentLayer.delete tests
# ---------------------------------------------------------------------------

class TestContentLayerDelete:
    def test_delete_by_author(self):
        layer = _make_layer()
        sig = CreatorSignature()
        item = layer.post("goodbye", author_sig=sig)
        result = layer.delete(item.content_id, requester_sig=sig)
        assert result is True
        assert layer.count() == 0

    def test_delete_by_different_creator_denied(self):
        """A signature with a different creator name cannot delete someone else's content."""
        import dataclasses
        layer = _make_layer()
        sig_a = CreatorSignature()
        item = layer.post("mine", author_sig=sig_a)

        # Create a signature that reports a different creator
        sig_b = dataclasses.replace(sig_a, creator="SomeoneElse")
        result = layer.delete(item.content_id, requester_sig=sig_b)
        assert result is False
        assert layer.get(item.content_id) is not None

    def test_delete_missing_returns_false(self):
        layer = _make_layer()
        sig = CreatorSignature()
        assert layer.delete("nonexistent", requester_sig=sig) is False

    def test_delete_records_ledger_event(self):
        ledger = LegacyLedger()
        layer = ContentLayer(ledger=ledger)
        sig = CreatorSignature()
        item = layer.post("byebye", author_sig=sig)
        layer.delete(item.content_id, requester_sig=sig)
        kinds = [e.event_kind for e in ledger.all_entries()]
        assert "content_deleted" in kinds


# ---------------------------------------------------------------------------
# ContentLayer.list tests
# ---------------------------------------------------------------------------

class TestContentLayerList:
    def test_list_returns_all_items(self):
        layer = _make_layer()
        layer.post("alpha")
        layer.post("beta")
        layer.post("gamma")
        items = layer.list()
        assert len(items) == 3

    def test_list_excludes_deleted(self):
        layer = _make_layer()
        sig = CreatorSignature()
        kept = layer.post("keep", author_sig=sig)
        gone = layer.post("gone", author_sig=sig)
        layer.delete(gone.content_id, requester_sig=sig)
        items = layer.list()
        ids = [it.content_id for it in items]
        assert kept.content_id in ids
        assert gone.content_id not in ids

    def test_list_respects_limit(self):
        layer = _make_layer()
        for i in range(10):
            layer.post(f"item-{i}")
        assert len(layer.list(limit=3)) == 3

    def test_list_after_ts_filter(self):
        layer = _make_layer()
        before = time.time()
        time.sleep(0.01)
        layer.post("recent")
        items = layer.list(after_ts=before)
        assert len(items) == 1
        assert items[0].body == "recent"

    def test_list_content_type_filter(self):
        layer = _make_layer()
        layer.post("text item", content_type="text")
        layer.post('{"key": "val"}', content_type="json")
        json_items = layer.list(content_type="json")
        assert all(it.content_type == "json" for it in json_items)
        assert len(json_items) == 1

    def test_list_ordered_by_created_at(self):
        layer = _make_layer()
        for i in range(5):
            layer.post(f"item-{i}")
            time.sleep(0.005)
        items = layer.list()
        for i in range(len(items) - 1):
            assert items[i].created_at <= items[i + 1].created_at
