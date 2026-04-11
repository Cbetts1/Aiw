"""Tests for the AIM Name Service (ANS) — registry and resolver."""

import time
import pytest

from aim.ans.registry import ANSRegistry, ANSRecord, _normalise, _validate
from aim.ans.resolver import ANSResolver
from aim.identity.signature import ORIGIN_CREATOR


# ---------------------------------------------------------------------------
# Name normalisation helpers
# ---------------------------------------------------------------------------

class TestNormalise:
    def test_strips_scheme(self):
        assert _normalise("aim://weather.public.aim") == "weather.public.aim"

    def test_lowercases(self):
        assert _normalise("Weather.Public.AIM") == "weather.public.aim"

    def test_strips_and_lowercases(self):
        assert _normalise("aim://WEATHER.PUBLIC.AIM") == "weather.public.aim"

    def test_no_scheme(self):
        assert _normalise("foo.aim") == "foo.aim"


class TestValidate:
    def test_valid_two_label(self):
        _validate("foo.aim")  # should not raise

    def test_valid_three_label(self):
        _validate("weather.public.aim")  # should not raise

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            _validate("")

    def test_too_long_raises(self):
        with pytest.raises(ValueError, match="must not exceed 253"):
            _validate("a" * 254)

    def test_single_label_raises(self):
        with pytest.raises(ValueError, match="at least two labels"):
            _validate("singlelabel")

    def test_empty_label_raises(self):
        with pytest.raises(ValueError, match="empty labels"):
            _validate("foo..aim")

    def test_label_too_long_raises(self):
        with pytest.raises(ValueError, match="must not exceed 63"):
            _validate(("a" * 64) + ".aim")

    def test_invalid_char_raises(self):
        with pytest.raises(ValueError, match="invalid character"):
            _validate("foo_bar.aim")

    def test_leading_hyphen_raises(self):
        with pytest.raises(ValueError, match="must not start or end with a hyphen"):
            _validate("-foo.aim")

    def test_trailing_hyphen_raises(self):
        with pytest.raises(ValueError, match="must not start or end with a hyphen"):
            _validate("foo-.aim")


# ---------------------------------------------------------------------------
# ANSRecord
# ---------------------------------------------------------------------------

class TestANSRecord:
    def test_name_normalised_on_init(self):
        r = ANSRecord("aim://Weather.Public.AIM", "node-1", "127.0.0.1", 7700)
        assert r.name == "weather.public.aim"

    def test_aim_uri_property(self):
        r = ANSRecord("weather.public.aim", "node-1", "127.0.0.1", 7700)
        assert r.aim_uri == "aim://weather.public.aim"

    def test_default_creator(self):
        r = ANSRecord("test.aim", "node-1", "127.0.0.1", 7700)
        assert r.creator == ORIGIN_CREATOR

    def test_default_ttl(self):
        r = ANSRecord("test.aim", "node-1", "127.0.0.1", 7700)
        assert r.ttl_seconds == 3600

    def test_registered_at_auto(self):
        before = time.time()
        r = ANSRecord("test.aim", "node-1", "127.0.0.1", 7700)
        after = time.time()
        assert before <= r.registered_at <= after

    def test_invalid_port_zero_raises(self):
        with pytest.raises(ValueError, match="Port must be between"):
            ANSRecord("test.aim", "node-1", "127.0.0.1", 0)

    def test_invalid_port_too_high_raises(self):
        with pytest.raises(ValueError, match="Port must be between"):
            ANSRecord("test.aim", "node-1", "127.0.0.1", 99999)

    def test_capabilities_stored(self):
        r = ANSRecord("test.aim", "n", "127.0.0.1", 7700, capabilities=["query", "task"])
        assert "query" in r.capabilities
        assert "task" in r.capabilities


# ---------------------------------------------------------------------------
# ANSRegistry
# ---------------------------------------------------------------------------

class TestANSRegistry:
    def setup_method(self):
        self.registry = ANSRegistry()

    def _record(self, name="test.aim", node_id="n1", host="127.0.0.1", port=7700) -> ANSRecord:
        return ANSRecord(name, node_id, host, port)

    def test_register_and_get(self):
        r = self._record()
        self.registry.register(r)
        found = self.registry.get("test.aim")
        assert found is not None
        assert found.node_id == "n1"

    def test_get_with_scheme_prefix(self):
        self.registry.register(self._record())
        found = self.registry.get("aim://test.aim")
        assert found is not None

    def test_get_case_insensitive(self):
        self.registry.register(self._record())
        found = self.registry.get("TEST.AIM")
        assert found is not None

    def test_deregister(self):
        self.registry.register(self._record())
        self.registry.deregister("test.aim")
        assert self.registry.get("test.aim") is None

    def test_deregister_nonexistent_is_noop(self):
        self.registry.deregister("does.not.exist")  # should not raise

    def test_all_records(self):
        self.registry.register(self._record("a.aim", "n1"))
        self.registry.register(self._record("b.aim", "n2"))
        assert self.registry.count() == 2
        names = {r.name for r in self.registry.all_records()}
        assert "a.aim" in names
        assert "b.aim" in names

    def test_find_by_capability(self):
        r1 = ANSRecord("search.aim", "n1", "127.0.0.1", 7700, capabilities=["query"])
        r2 = ANSRecord("compute.aim", "n2", "127.0.0.1", 7701, capabilities=["compute"])
        self.registry.register(r1)
        self.registry.register(r2)
        results = self.registry.find_by_capability("query")
        assert len(results) == 1
        assert results[0].name == "search.aim"

    def test_find_by_creator(self):
        r1 = ANSRecord("a.aim", "n1", "127.0.0.1", 7700, creator="Cbetts1")
        r2 = ANSRecord("b.aim", "n2", "127.0.0.1", 7701, creator="other")
        self.registry.register(r1)
        self.registry.register(r2)
        results = self.registry.find_by_creator("Cbetts1")
        assert len(results) == 1
        assert results[0].name == "a.aim"

    def test_overwrite_on_re_register(self):
        self.registry.register(ANSRecord("test.aim", "old-id", "127.0.0.1", 7700))
        self.registry.register(ANSRecord("test.aim", "new-id", "127.0.0.1", 7700))
        found = self.registry.get("test.aim")
        assert found.node_id == "new-id"

    def test_count(self):
        for i in range(5):
            self.registry.register(self._record(f"node{i}.aim", f"n{i}", port=7700 + i))
        assert self.registry.count() == 5

    def test_clear(self):
        self.registry.register(self._record())
        self.registry.clear()
        assert self.registry.count() == 0


# ---------------------------------------------------------------------------
# ANSResolver
# ---------------------------------------------------------------------------

class TestANSResolver:
    def setup_method(self):
        self.registry = ANSRegistry()
        self.resolver = ANSResolver(self.registry)

    def test_resolve_returns_node_record(self):
        self.registry.register(
            ANSRecord("weather.aim", "uuid-1", "10.0.0.1", 8000, capabilities=["query"])
        )
        node = self.resolver.resolve("weather.aim")
        assert node is not None
        assert node.host == "10.0.0.1"
        assert node.port == 8000
        assert node.node_id == "uuid-1"

    def test_resolve_with_scheme(self):
        self.registry.register(ANSRecord("foo.aim", "uuid-2", "10.0.0.2", 8001))
        node = self.resolver.resolve("aim://foo.aim")
        assert node is not None
        assert node.host == "10.0.0.2"

    def test_resolve_unknown_returns_none(self):
        assert self.resolver.resolve("unknown.aim") is None

    def test_resolve_ans_raw(self):
        r = ANSRecord("raw.aim", "uuid-3", "10.0.0.3", 8002)
        self.registry.register(r)
        ans = self.resolver.resolve_ans("raw.aim")
        assert ans is not None
        assert ans.aim_uri == "aim://raw.aim"

    def test_expired_record_returns_none(self):
        # Register with tiny TTL already exceeded
        r = ANSRecord("old.aim", "uuid-4", "10.0.0.4", 8003, ttl_seconds=1)
        # Back-date the registration so it is already expired
        r.registered_at = time.time() - 10
        self.registry.register(r)
        assert self.resolver.resolve("old.aim") is None

    def test_expired_record_removed_from_registry(self):
        r = ANSRecord("expired.aim", "uuid-5", "10.0.0.5", 8004, ttl_seconds=1)
        r.registered_at = time.time() - 10
        self.registry.register(r)
        self.resolver.resolve("expired.aim")
        # Should have been pruned from registry
        assert self.registry.get("expired.aim") is None

    def test_capabilities_preserved_in_node_record(self):
        self.registry.register(
            ANSRecord("cap.aim", "uuid-6", "10.0.0.6", 8005, capabilities=["compute", "query"])
        )
        node = self.resolver.resolve("cap.aim")
        assert "compute" in node.capabilities
        assert "query" in node.capabilities
