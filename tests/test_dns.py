"""Tests for the AIM DNS Bridge."""

from __future__ import annotations

import uuid

import pytest

from aim.dns.bridge import DNSBridge, BridgeResult
from aim.ans.registry import ANSRegistry, ANSRecord
from aim.identity.signature import ORIGIN_CREATOR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_bridge() -> tuple[DNSBridge, ANSRegistry]:
    registry = ANSRegistry()
    bridge   = DNSBridge(registry=registry)
    return bridge, registry


def _seed_record(
    registry: ANSRegistry,
    name: str = "test.aim",
    host: str = "10.0.0.1",
    port: int = 7700,
    caps: list[str] | None = None,
) -> ANSRecord:
    r = ANSRecord(name, str(uuid.uuid4()), host, port, capabilities=caps or [])
    registry.register(r)
    return r


# ---------------------------------------------------------------------------
# BridgeResult
# ---------------------------------------------------------------------------

class TestBridgeResult:
    def test_to_dict_keys(self):
        br = BridgeResult(name="foo.aim", host="10.0.0.1", port=7700,
                          node_id="nid", aim_uri="aim://foo.aim",
                          source="ans", capabilities=["query"])
        d = br.to_dict()
        assert d["name"]         == "foo.aim"
        assert d["host"]         == "10.0.0.1"
        assert d["port"]         == 7700
        assert d["node_id"]      == "nid"
        assert d["aim_uri"]      == "aim://foo.aim"
        assert d["source"]       == "ans"
        assert d["capabilities"] == ["query"]

    def test_default_capabilities_empty_list(self):
        br = BridgeResult(name="x.aim", host="1.2.3.4", port=7700)
        assert br.capabilities == []


# ---------------------------------------------------------------------------
# aim_to_dns / dns_to_aim (static methods)
# ---------------------------------------------------------------------------

class TestNameConversion:
    def test_aim_to_dns_strips_scheme(self):
        assert DNSBridge.aim_to_dns("aim://weather.public.aim") == "weather.public.aim"

    def test_aim_to_dns_bare_name_unchanged(self):
        assert DNSBridge.aim_to_dns("weather.public.aim") == "weather.public.aim"

    def test_dns_to_aim_appends_dot_aim(self):
        assert DNSBridge.dns_to_aim("weather.example.com") == "aim://weather.example.com.aim"

    def test_dns_to_aim_preserves_dot_aim_suffix(self):
        assert DNSBridge.dns_to_aim("weather.public.aim") == "aim://weather.public.aim"

    def test_dns_to_aim_lowercases(self):
        result = DNSBridge.dns_to_aim("Weather.Public.AIM")
        assert result == "aim://weather.public.aim"


# ---------------------------------------------------------------------------
# resolve — ANS path
# ---------------------------------------------------------------------------

class TestResolveANS:
    def test_resolve_aim_uri_from_ans(self):
        bridge, registry = _fresh_bridge()
        _seed_record(registry, "weather.public.aim", host="10.0.0.5", port=8000)
        result = bridge.resolve("aim://weather.public.aim")
        assert result is not None
        assert result.source == "ans"
        assert result.host   == "10.0.0.5"
        assert result.port   == 8000

    def test_resolve_bare_aim_name(self):
        bridge, registry = _fresh_bridge()
        _seed_record(registry, "compute.aim", host="10.0.0.6", port=7701)
        result = bridge.resolve("compute.aim")
        assert result is not None
        assert result.source == "ans"
        assert result.aim_uri == "aim://compute.aim"

    def test_resolve_unknown_aim_name_returns_none(self):
        bridge, _ = _fresh_bridge()
        result = bridge.resolve("aim://unknown.aim")
        assert result is None

    def test_resolve_returns_capabilities(self):
        bridge, registry = _fresh_bridge()
        _seed_record(registry, "cap.aim", caps=["query", "task"])
        result = bridge.resolve("cap.aim")
        assert result is not None
        assert "query" in result.capabilities
        assert "task"  in result.capabilities

    def test_resolve_aim_name_contains_node_id(self):
        bridge, registry = _fresh_bridge()
        record = _seed_record(registry, "nodeid.aim")
        result = bridge.resolve("nodeid.aim")
        assert result is not None
        assert result.node_id == record.node_id


# ---------------------------------------------------------------------------
# resolve — DNS fallback
# ---------------------------------------------------------------------------

class TestResolveDNSFallback:
    def test_resolve_localhost_via_dns(self):
        bridge, _ = _fresh_bridge()
        result = bridge.resolve("localhost", default_port=9999)
        assert result is not None
        assert result.source == "dns"
        assert result.host in ("127.0.0.1", "::1", "localhost")
        assert result.port == 9999

    def test_resolve_unresolvable_returns_none(self):
        bridge, _ = _fresh_bridge()
        result = bridge.resolve("this-host-does-not-exist.invalid")
        assert result is None


# ---------------------------------------------------------------------------
# register_from_dns
# ---------------------------------------------------------------------------

class TestRegisterFromDNS:
    def test_register_classical_hostname_creates_ans_record(self):
        bridge, registry = _fresh_bridge()
        node_id = str(uuid.uuid4())
        record  = bridge.register_from_dns("localhost", node_id=node_id, port=7700)
        assert record.aim_uri == "aim://localhost.aim"
        assert record.port    == 7700
        # Verify it ended up in the registry
        found = registry.get("localhost.aim")
        assert found is not None
        assert found.node_id == node_id

    def test_register_already_aim_hostname(self):
        bridge, registry = _fresh_bridge()
        node_id = str(uuid.uuid4())
        record  = bridge.register_from_dns("weather.public.aim", node_id=node_id, port=7701)
        assert record.name == "weather.public.aim"
        found = registry.get("weather.public.aim")
        assert found is not None

    def test_register_with_capabilities(self):
        bridge, registry = _fresh_bridge()
        node_id = str(uuid.uuid4())
        record  = bridge.register_from_dns(
            "localhost", node_id=node_id, port=7702, capabilities=["query", "task"]
        )
        assert "query" in record.capabilities
        assert "task"  in record.capabilities

    def test_register_creator_propagated(self):
        bridge, registry = _fresh_bridge()
        node_id = str(uuid.uuid4())
        record  = bridge.register_from_dns("localhost", node_id=node_id, port=7703,
                                            creator="Cbetts1")
        assert record.creator == "Cbetts1"


# ---------------------------------------------------------------------------
# list_ans_records
# ---------------------------------------------------------------------------

class TestListANSRecords:
    def test_empty_registry(self):
        bridge, _ = _fresh_bridge()
        assert bridge.list_ans_records() == []

    def test_returns_all_records(self):
        bridge, registry = _fresh_bridge()
        _seed_record(registry, "a.aim")
        _seed_record(registry, "b.aim")
        records = bridge.list_ans_records()
        names = {r["name"] for r in records}
        assert "a.aim" in names
        assert "b.aim" in names

    def test_record_fields_present(self):
        bridge, registry = _fresh_bridge()
        _seed_record(registry, "field.aim", host="1.2.3.4", port=8080)
        records = bridge.list_ans_records()
        assert len(records) == 1
        r = records[0]
        for key in ("name", "aim_uri", "node_id", "host", "port",
                    "capabilities", "creator", "ttl_seconds"):
            assert key in r, f"Missing key: {key}"

    def test_record_aim_uri_correct(self):
        bridge, registry = _fresh_bridge()
        _seed_record(registry, "uri.aim")
        records = bridge.list_ans_records()
        assert records[0]["aim_uri"] == "aim://uri.aim"
