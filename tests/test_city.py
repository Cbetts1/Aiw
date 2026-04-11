"""Tests for the AIM City governance module."""

from __future__ import annotations

import pytest

from aim.node.registry import NodeRegistry, NodeRecord
from aim.identity.ledger import LegacyLedger
from aim.identity.signature import CreatorSignature, ORIGIN_CREATOR
from aim.protocol.message import AIMMessage, Intent
from aim.city.roles import CityRole, CityEventKind
from aim.city.governor import CityGovernorBot
from aim.city.citizen import CitizenNode
from aim.city.protector import ProtectionAgent
from aim.city.builder import BuilderBot
from aim.city.educator import EducationBot
from aim.city.architect import ArchitectBot
from aim.city.integrity import IntegrityGuard
from aim.city.launcher import CityLauncher, CityConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_registry() -> NodeRegistry:
    return NodeRegistry()


def _fresh_ledger() -> LegacyLedger:
    return LegacyLedger()


# ---------------------------------------------------------------------------
# CityGovernorBot
# ---------------------------------------------------------------------------

class TestCityGovernorBot:
    def _make(self) -> CityGovernorBot:
        return CityGovernorBot(
            port=19800,
            registry=_fresh_registry(),
            ledger=_fresh_ledger(),
        )

    def test_role(self):
        gov = self._make()
        assert gov.ROLE == CityRole.GOVERNOR

    def test_capabilities_include_governor(self):
        gov = self._make()
        assert "governor" in gov.capabilities

    def test_creator_is_origin(self):
        gov = self._make()
        assert gov.creator == ORIGIN_CREATOR

    def test_get_city_status_initial(self):
        gov = self._make()
        status = gov.get_city_status()
        assert status["role"] == "governor"
        assert status["bots"] == 0
        assert status["citizens"] == 0
        assert status["alerts"] == 0
        assert status["policies"] == 0

    @pytest.mark.asyncio
    async def test_task_city_status(self):
        gov = self._make()
        result = await gov._task_city_status({})
        assert result["role"] == "governor"
        assert result["creator"] == ORIGIN_CREATOR

    @pytest.mark.asyncio
    async def test_task_issue_policy(self):
        gov = self._make()
        result = await gov._task_issue_policy({"policy": "All nodes must carry valid signatures."})
        assert result["status"] == "ok"
        assert result["total_policies"] == 1

    @pytest.mark.asyncio
    async def test_task_issue_policy_missing_text(self):
        gov = self._make()
        result = await gov._task_issue_policy({})
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_task_raise_alert(self):
        gov = self._make()
        result = await gov._task_raise_alert({"message": "Rogue node detected", "level": "high"})
        assert result["status"] == "ok"
        assert result["total_alerts"] == 1

    @pytest.mark.asyncio
    async def test_task_register_bot(self):
        gov = self._make()
        result = await gov._task_register_bot({
            "node_id": "bot-001",
            "role": "protector",
            "host": "127.0.0.1",
            "port": 7801,
        })
        assert result["status"] == "ok"
        assert result["role"] == "protector"

    @pytest.mark.asyncio
    async def test_task_register_bot_missing_id(self):
        gov = self._make()
        result = await gov._task_register_bot({})
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_task_citizen_join(self):
        gov = self._make()
        result = await gov._task_citizen_join({"citizen_id": "c-001", "name": "Alice"})
        assert result["status"] == "ok"
        assert "Alice" in result["welcome"]

    @pytest.mark.asyncio
    async def test_task_citizen_join_missing_id(self):
        gov = self._make()
        result = await gov._task_citizen_join({"name": "Alice"})
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_task_citizen_leave(self):
        gov = self._make()
        await gov._task_citizen_join({"citizen_id": "c-002", "name": "Bob"})
        result = await gov._task_citizen_leave({"citizen_id": "c-002"})
        assert result["status"] == "ok"
        assert "c-002" not in gov._entities

    @pytest.mark.asyncio
    async def test_task_list_bots(self):
        gov = self._make()
        await gov._task_register_bot({"node_id": "b-001", "role": "builder", "port": 7802})
        await gov._task_register_bot({"node_id": "b-002", "role": "educator", "port": 7803})
        result = await gov._task_list_bots({})
        assert len(result["bots"]) == 2

    @pytest.mark.asyncio
    async def test_task_list_bots_with_role_filter(self):
        gov = self._make()
        await gov._task_register_bot({"node_id": "b-001", "role": "builder", "port": 7802})
        await gov._task_register_bot({"node_id": "b-002", "role": "educator", "port": 7803})
        result = await gov._task_list_bots({"role": "builder"})
        assert len(result["bots"]) == 1

    @pytest.mark.asyncio
    async def test_query_handler_uses_engine(self):
        gov = self._make()
        msg = AIMMessage.query("tell me about the governor", sender_id="cli")
        response = await gov._handler.dispatch(msg)
        assert response is not None
        assert "governor" in response.payload["result"]["answer"].lower()

    def test_ledger_records_bot_deployed_on_init(self):
        ledger = _fresh_ledger()
        gov = CityGovernorBot(port=19801, registry=_fresh_registry(), ledger=ledger)
        entries = ledger.entries_by_kind(CityEventKind.BOT_DEPLOYED)
        assert any(e.node_id == gov.node_id for e in entries)


# ---------------------------------------------------------------------------
# CitizenNode
# ---------------------------------------------------------------------------

class TestCitizenNode:
    def _make(self, name: str = "Alice") -> CitizenNode:
        return CitizenNode(
            port=19810,
            name=name,
            ledger=_fresh_ledger(),
        )

    def test_role(self):
        c = self._make()
        assert c.ROLE == CityRole.CITIZEN

    def test_capabilities_include_citizen(self):
        c = self._make()
        assert "citizen" in c.capabilities

    def test_name_stored(self):
        c = self._make("Charlie")
        assert c.name == "Charlie"

    @pytest.mark.asyncio
    async def test_query_includes_citizen_metadata(self):
        c = self._make("Dave")
        msg = AIMMessage.query("who am i", sender_id="cli")
        response = await c._handler.dispatch(msg)
        result = response.payload["result"]
        assert result["role"] == "citizen"
        assert result["name"] == "Dave"

    def test_ledger_records_citizen_joined(self):
        ledger = _fresh_ledger()
        c = CitizenNode(port=19811, name="Eve", ledger=ledger)
        entries = ledger.entries_by_kind(CityEventKind.CITIZEN_JOINED)
        assert any(e.node_id == c.node_id for e in entries)


# ---------------------------------------------------------------------------
# ProtectionAgent
# ---------------------------------------------------------------------------

class TestProtectionAgent:
    def _make(self, registry: NodeRegistry | None = None) -> ProtectionAgent:
        return ProtectionAgent(
            port=19820,
            registry=registry or _fresh_registry(),
            ledger=_fresh_ledger(),
        )

    def test_role(self):
        p = self._make()
        assert p.ROLE == CityRole.PROTECTOR

    def test_capabilities_include_protect(self):
        p = self._make()
        assert "protect" in p.capabilities

    @pytest.mark.asyncio
    async def test_audit_registry_clean(self):
        reg = _fresh_registry()
        reg.register(NodeRecord("n1", "127.0.0.1", 7700, creator=ORIGIN_CREATOR))
        reg.register(NodeRecord("n2", "127.0.0.1", 7701, creator=ORIGIN_CREATOR))
        p = ProtectionAgent(port=19821, registry=reg, ledger=_fresh_ledger())
        result = await p._task_audit_registry({})
        assert result["violations"] == 0
        assert result["nodes_checked"] == 2

    @pytest.mark.asyncio
    async def test_audit_registry_detects_bad_creator(self):
        reg = _fresh_registry()
        reg.register(NodeRecord("n-rogue", "127.0.0.1", 7702, creator="Hacker"))
        p = ProtectionAgent(port=19822, registry=reg, ledger=_fresh_ledger())
        result = await p._task_audit_registry({})
        assert result["violations"] == 1

    @pytest.mark.asyncio
    async def test_blacklist_node(self):
        p = self._make()
        result = await p._task_blacklist_node({"node_id": "evil-node", "reason": "test"})
        assert result["blacklisted"] is True
        assert p.is_blacklisted("evil-node")

    @pytest.mark.asyncio
    async def test_blacklist_node_missing_id(self):
        p = self._make()
        result = await p._task_blacklist_node({})
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_check_signature_valid(self):
        sig = CreatorSignature()
        p = self._make()
        result = await p._task_check_signature({"signature": sig.to_dict()})
        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_check_signature_tampered(self):
        sig_dict = CreatorSignature().to_dict()
        sig_dict["creator"] = "Hacker"
        # Recompute is not done — digest mismatch
        p = self._make()
        result = await p._task_check_signature({"signature": sig_dict})
        assert result["valid"] is False

    @pytest.mark.asyncio
    async def test_threat_report(self):
        p = self._make()
        await p._task_blacklist_node({"node_id": "x", "reason": "test"})
        result = await p._task_threat_report({})
        assert result["blacklisted_count"] == 1
        assert len(result["threats"]) == 1

    def test_not_blacklisted_initially(self):
        p = self._make()
        assert not p.is_blacklisted("some-node")


# ---------------------------------------------------------------------------
# BuilderBot
# ---------------------------------------------------------------------------

class TestBuilderBot:
    def _make(self, registry: NodeRegistry | None = None) -> BuilderBot:
        return BuilderBot(
            port=19830,
            registry=registry or _fresh_registry(),
            ledger=_fresh_ledger(),
        )

    def test_role(self):
        b = self._make()
        assert b.ROLE == CityRole.BUILDER

    def test_capabilities_include_build(self):
        b = self._make()
        assert "build" in b.capabilities

    @pytest.mark.asyncio
    async def test_build_node_registers_in_registry(self):
        reg = _fresh_registry()
        b   = BuilderBot(port=19831, registry=reg, ledger=_fresh_ledger())
        result = await b._task_build_node({
            "node_id": "worker-1",
            "host": "127.0.0.1",
            "port": 7900,
            "capabilities": ["compute"],
            "role": "worker",
        })
        assert result["status"] == "ok"
        assert reg.get("worker-1") is not None

    @pytest.mark.asyncio
    async def test_build_node_missing_port(self):
        b = self._make()
        result = await b._task_build_node({"node_id": "x"})
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_build_node_auto_generates_id(self):
        reg = _fresh_registry()
        b   = BuilderBot(port=19832, registry=reg, ledger=_fresh_ledger())
        result = await b._task_build_node({"port": 7901})
        assert result["status"] == "ok"
        assert len(result["node_id"]) > 0

    @pytest.mark.asyncio
    async def test_build_status(self):
        reg = _fresh_registry()
        b   = BuilderBot(port=19833, registry=reg, ledger=_fresh_ledger())
        await b._task_build_node({"port": 7902})
        result = await b._task_build_status({})
        assert result["builds_completed"] == 1

    @pytest.mark.asyncio
    async def test_list_builds(self):
        b = self._make()
        await b._task_build_node({"port": 7903})
        result = await b._task_list_builds({})
        assert len(result["builds"]) == 1

    def test_ledger_records_bot_deployed(self):
        ledger = _fresh_ledger()
        b = BuilderBot(port=19834, registry=_fresh_registry(), ledger=ledger)
        entries = ledger.entries_by_kind(CityEventKind.BOT_DEPLOYED)
        assert any(e.node_id == b.node_id for e in entries)


# ---------------------------------------------------------------------------
# EducationBot
# ---------------------------------------------------------------------------

class TestEducationBot:
    def _make(self, extra: dict | None = None) -> EducationBot:
        return EducationBot(
            port=19840,
            knowledge=extra,
            ledger=_fresh_ledger(),
        )

    def test_role(self):
        e = self._make()
        assert e.ROLE == CityRole.EDUCATOR

    def test_capabilities_include_educate(self):
        e = self._make()
        assert "educate" in e.capabilities

    def test_default_topics_loaded(self):
        e = self._make()
        assert "aim" in e._knowledge
        assert "city" in e._knowledge
        assert "security" in e._knowledge

    @pytest.mark.asyncio
    async def test_lookup_known_topic(self):
        e = self._make()
        result = await e._task_lookup({"keyword": "aim"})
        assert result["status"] == "ok"
        assert "AIM" in result["content"]

    @pytest.mark.asyncio
    async def test_lookup_unknown_topic(self):
        e = self._make()
        result = await e._task_lookup({"keyword": "nonexistent_topic_xyz"})
        assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_teach_new_topic(self):
        e = self._make()
        result = await e._task_teach({"keyword": "robot", "response": "Robots are automated machines."})
        assert result["status"] == "ok"
        assert "robot" in e._knowledge

    @pytest.mark.asyncio
    async def test_teach_missing_fields(self):
        e = self._make()
        result = await e._task_teach({"keyword": "only_keyword"})
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_list_topics(self):
        e = self._make()
        result = await e._task_list_topics({})
        assert "aim" in result["topics"]
        assert result["total"] >= len(result["topics"])

    @pytest.mark.asyncio
    async def test_query_uses_knowledge_engine(self):
        e = self._make()
        msg = AIMMessage.query("tell me about aim", sender_id="cli")
        response = await e._handler.dispatch(msg)
        assert "AIM" in response.payload["result"]["answer"]

    def test_extra_knowledge_merged(self):
        e = self._make(extra={"custom_topic": "Custom answer."})
        assert "custom_topic" in e._knowledge


# ---------------------------------------------------------------------------
# ArchitectBot
# ---------------------------------------------------------------------------

class TestArchitectBot:
    def _make(self, registry: NodeRegistry | None = None) -> ArchitectBot:
        return ArchitectBot(
            port=19850,
            registry=registry or _fresh_registry(),
            ledger=_fresh_ledger(),
        )

    def test_role(self):
        a = self._make()
        assert a.ROLE == CityRole.ARCHITECT

    def test_capabilities_include_design(self):
        a = self._make()
        assert "design" in a.capabilities

    @pytest.mark.asyncio
    async def test_create_blueprint(self):
        a = self._make()
        result = await a._task_create_blueprint({
            "name": "phase-1",
            "nodes": [
                {"role": "governor", "host": "127.0.0.1", "port": 7800},
                {"role": "protector", "host": "127.0.0.1", "port": 7801},
            ],
        })
        assert result["status"] == "ok"
        assert result["blueprint"]["name"] == "phase-1"

    @pytest.mark.asyncio
    async def test_create_blueprint_missing_nodes(self):
        a = self._make()
        result = await a._task_create_blueprint({"name": "empty"})
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_analyse_topology_empty_registry(self):
        a = self._make(registry=_fresh_registry())
        result = await a._task_analyse_topology({})
        assert result["total_nodes"] == 0
        # All required capabilities are missing → recommendations should be non-empty
        assert len(result["recommendations"]) > 0

    @pytest.mark.asyncio
    async def test_analyse_topology_complete_city(self):
        reg = _fresh_registry()
        for i, cap in enumerate(["governor", "protect", "build", "educate", "design"]):
            reg.register(NodeRecord(f"n-{i}", "127.0.0.1", 7800 + i, [cap]))
        a = ArchitectBot(port=19851, registry=reg, ledger=_fresh_ledger())
        result = await a._task_analyse_topology({})
        assert result["recommendations"][0].startswith("City topology is complete")

    @pytest.mark.asyncio
    async def test_list_blueprints(self):
        a = self._make()
        await a._task_create_blueprint({
            "name": "bp1",
            "nodes": [{"role": "worker", "port": 7900}],
        })
        result = await a._task_list_blueprints({})
        assert len(result["blueprints"]) == 1


# ---------------------------------------------------------------------------
# IntegrityGuard
# ---------------------------------------------------------------------------

class TestIntegrityGuard:
    def _make(self) -> IntegrityGuard:
        return IntegrityGuard(registry=_fresh_registry(), ledger=_fresh_ledger())

    def test_snapshot_returns_hex_digest(self):
        g = self._make()
        digest = g.snapshot("cfg", {"key": "value"})
        assert len(digest) == 64  # SHA-256 hex

    def test_verify_unchanged_data(self):
        g    = self._make()
        data = {"nodes": ["n1", "n2"]}
        g.snapshot("nodes", data)
        assert g.verify("nodes", data) is True

    def test_verify_detects_tampering(self):
        g    = self._make()
        data = {"nodes": ["n1", "n2"]}
        g.snapshot("nodes", data)
        tampered = {"nodes": ["n1", "n2", "INTRUDER"]}
        assert g.verify("nodes", tampered) is False

    def test_verify_no_prior_snapshot_takes_one(self):
        g = self._make()
        assert g.verify("fresh", {"x": 1}) is True
        assert "fresh" in g._checksums

    def test_audit_ledger_clean(self):
        ledger = _fresh_ledger()
        guard  = IntegrityGuard(registry=_fresh_registry(), ledger=ledger)
        report = guard.audit_ledger()
        assert report["integrity"] == "ok"

    def test_audit_registry_clean(self):
        reg = _fresh_registry()
        reg.register(NodeRecord("n1", "127.0.0.1", 7700, creator=ORIGIN_CREATOR))
        guard  = IntegrityGuard(registry=reg, ledger=_fresh_ledger())
        report = guard.audit_registry()
        assert report["integrity"] == "ok"
        assert report["total_nodes"] == 1

    def test_audit_registry_detects_rogue(self):
        reg = _fresh_registry()
        reg.register(NodeRecord("rogue", "127.0.0.1", 7700, creator="Hacker"))
        guard  = IntegrityGuard(registry=reg, ledger=_fresh_ledger())
        report = guard.audit_registry()
        assert report["integrity"] == "violated"
        assert "rogue" in report["violations"]

    def test_full_report_structure(self):
        g      = self._make()
        report = g.full_report()
        assert "checksums_tracked"    in report
        assert "violations_detected"  in report
        assert "signature"            in report
        assert report["creator"]      == ORIGIN_CREATOR

    def test_tampering_increments_violations(self):
        g = self._make()
        g.snapshot("x", {"a": 1})
        g.verify("x", {"a": 2})
        report = g.full_report()
        assert report["violations_detected"] == 1


# ---------------------------------------------------------------------------
# CityLauncher — basic wiring test (no network)
# ---------------------------------------------------------------------------

class TestCityLauncher:
    def test_launcher_creates_five_bots(self):
        launcher = CityLauncher(CityConfig(
            host="127.0.0.1",
            governor_port=19860,
            protector_port=19861,
            builder_port=19862,
            educator_port=19863,
            architect_port=19864,
        ))
        # Manually build bots without calling launch() (which starts servers)
        cfg = launcher.config
        from aim.city.governor  import CityGovernorBot
        from aim.city.protector import ProtectionAgent
        from aim.city.builder   import BuilderBot
        from aim.city.educator  import EducationBot
        from aim.city.architect import ArchitectBot

        governor  = CityGovernorBot(host=cfg.host, port=cfg.governor_port,   registry=launcher._registry, ledger=launcher._ledger)
        protector = ProtectionAgent(host=cfg.host, port=cfg.protector_port,  registry=launcher._registry, ledger=launcher._ledger)
        builder   = BuilderBot(     host=cfg.host, port=cfg.builder_port,    registry=launcher._registry, ledger=launcher._ledger)
        educator  = EducationBot(   host=cfg.host, port=cfg.educator_port,                                ledger=launcher._ledger)
        architect = ArchitectBot(   host=cfg.host, port=cfg.architect_port,  registry=launcher._registry, ledger=launcher._ledger)

        assert governor.ROLE  == CityRole.GOVERNOR
        assert protector.ROLE == CityRole.PROTECTOR
        assert builder.ROLE   == CityRole.BUILDER
        assert educator.ROLE  == CityRole.EDUCATOR
        assert architect.ROLE == CityRole.ARCHITECT

    def test_integrity_report_initial(self):
        launcher = CityLauncher(CityConfig())
        report   = launcher.integrity_report()
        assert report["creator"] == ORIGIN_CREATOR
        assert report["violations_detected"] == 0

    def test_city_config_defaults(self):
        cfg = CityConfig()
        assert cfg.host           == "127.0.0.1"
        assert cfg.governor_port  == 7800
        assert cfg.protector_port == 7801
        assert cfg.builder_port   == 7802
        assert cfg.educator_port  == 7803
        assert cfg.architect_port == 7804
