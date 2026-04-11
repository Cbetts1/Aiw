"""Tests for the AIM Identity and Legacy Layer."""

import pytest

from aim.identity.signature import CreatorSignature, ORIGIN_CREATOR, AIM_MESH_NAME
from aim.identity.ledger import LegacyLedger, LedgerEntry, EventKind


# ---------------------------------------------------------------------------
# CreatorSignature
# ---------------------------------------------------------------------------

class TestCreatorSignature:
    def test_default_fields(self):
        sig = CreatorSignature()
        assert sig.creator == ORIGIN_CREATOR
        assert sig.mesh == AIM_MESH_NAME
        assert sig.epoch == "1991"
        assert len(sig.digest) == 64  # SHA-256 hex digest

    def test_verify_self(self):
        sig = CreatorSignature()
        assert sig.verify() is True

    def test_tamper_detection(self):
        sig = CreatorSignature()
        sig.creator = "impostor"
        assert sig.verify() is False

    def test_unique_digests(self):
        digests = {CreatorSignature().digest for _ in range(50)}
        assert len(digests) == 50  # each node_id is unique → unique digest

    def test_str_representation(self):
        sig = CreatorSignature()
        s = str(sig)
        assert ORIGIN_CREATOR in s
        assert AIM_MESH_NAME in s

    def test_to_dict_round_trip(self):
        sig = CreatorSignature()
        d = sig.to_dict()
        assert d["creator"] == ORIGIN_CREATOR
        assert "digest" in d

    def test_from_dict_valid(self):
        sig = CreatorSignature()
        d = sig.to_dict()
        restored = CreatorSignature.from_dict(d)
        assert restored.verify()
        assert restored.creator == ORIGIN_CREATOR

    def test_from_dict_tampered_raises(self):
        sig = CreatorSignature()
        d = sig.to_dict()
        d["digest"] = "0" * 64  # wrong digest
        with pytest.raises(ValueError, match="Signature digest mismatch"):
            CreatorSignature.from_dict(d)


# ---------------------------------------------------------------------------
# LegacyLedger
# ---------------------------------------------------------------------------

class TestLegacyLedger:
    def setup_method(self):
        self.ledger = LegacyLedger()

    def test_record_and_retrieve(self):
        self.ledger.record(EventKind.NODE_CREATED, "node-1")
        entries = self.ledger.all_entries()
        assert len(entries) == 1
        assert entries[0].event_kind == EventKind.NODE_CREATED
        assert entries[0].node_id == "node-1"
        assert entries[0].creator == "Cbetts1"

    def test_entries_for_node(self):
        self.ledger.record(EventKind.NODE_CREATED, "node-a")
        self.ledger.record(EventKind.TASK_EXECUTED, "node-b")
        self.ledger.record(EventKind.MESSAGE_ROUTED, "node-a")
        result = self.ledger.entries_for_node("node-a")
        assert len(result) == 2

    def test_entries_by_kind(self):
        self.ledger.record(EventKind.NODE_CREATED, "n1")
        self.ledger.record(EventKind.NODE_CREATED, "n2")
        self.ledger.record(EventKind.TASK_EXECUTED, "n1")
        created = self.ledger.entries_by_kind(EventKind.NODE_CREATED)
        assert len(created) == 2

    def test_count(self):
        for i in range(7):
            self.ledger.record(EventKind.CUSTOM, f"node-{i}")
        assert self.ledger.count() == 7

    def test_signature_digest_stored(self):
        sig = CreatorSignature()
        entry = self.ledger.record(EventKind.NODE_CREATED, "n", signature=sig)
        assert entry.signature_digest == sig.digest

    def test_payload_preserved(self):
        self.ledger.record(EventKind.CUSTOM, "n", payload={"key": "value", "num": 42})
        entry = self.ledger.all_entries()[0]
        assert entry.payload["key"] == "value"
        assert entry.payload["num"] == 42

    def test_to_json(self):
        import json
        self.ledger.record(EventKind.NODE_CREATED, "n1")
        data = json.loads(self.ledger.to_json())
        assert len(data) == 1
        assert data[0]["node_id"] == "n1"

    def test_file_persistence(self, tmp_path):
        path = str(tmp_path / "ledger.jsonl")
        l1 = LegacyLedger(persist_path=path)
        l1.record(EventKind.NODE_CREATED, "persistent-node")

        # Load from file in a new instance
        l2 = LegacyLedger(persist_path=path)
        entries = l2.all_entries()
        assert len(entries) == 1
        assert entries[0].node_id == "persistent-node"
