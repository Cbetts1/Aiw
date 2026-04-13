"""Tests for the AIM Command Center module."""

from __future__ import annotations

import pytest

from aim.command_center.identity import VirtualDeviceIdentity
from aim.command_center.client import CommandCenterClient
from aim.health.reporter import HealthReporter, HealthSnapshot
from aim.health.metrics import SystemMetrics


# ---------------------------------------------------------------------------
# VirtualDeviceIdentity
# ---------------------------------------------------------------------------

class TestVirtualDeviceIdentity:
    def test_new_creates_valid_identity(self):
        ident = VirtualDeviceIdentity.new(
            name="test-device",
            repo_url="https://github.com/Cbetts1/Aiw",
            capabilities=["query", "task"],
        )
        assert ident.device_id
        assert ident.device_name == "test-device"
        assert ident.creator == "Cbetts1"
        assert ident.mesh_name == "AIM"
        assert "query" in ident.capabilities

    def test_verify_returns_true(self):
        ident = VirtualDeviceIdentity.new(
            name="verify-device",
            repo_url="https://github.com/Cbetts1/Aiw",
        )
        assert ident.verify() is True

    def test_to_dict_has_expected_keys(self):
        ident = VirtualDeviceIdentity.new(
            name="dict-device",
            repo_url="https://github.com/Cbetts1/Aiw",
            capabilities=["relay"],
        )
        d = ident.to_dict()
        for key in ("device_id", "device_name", "mesh_name", "creator",
                    "repo_url", "capabilities", "registered_at", "signature"):
            assert key in d, f"Missing key: {key}"

    def test_str_format(self):
        ident = VirtualDeviceIdentity.new(name="str-test", repo_url="https://x.y")
        s = str(ident)
        assert s.startswith("AIM-NODE:")
        assert "@str-test" in s

    def test_capabilities_defaults_to_empty(self):
        ident = VirtualDeviceIdentity.new(name="empty-caps", repo_url="https://x.y")
        assert ident.capabilities == []


# ---------------------------------------------------------------------------
# CommandCenterClient
# ---------------------------------------------------------------------------

class TestCommandCenterClient:
    def _make_client(self) -> CommandCenterClient:
        ident = VirtualDeviceIdentity.new(
            name="client-device",
            repo_url="https://github.com/Cbetts1/Aiw",
        )
        return CommandCenterClient(
            cc_host="127.0.0.1",
            cc_port=9999,
            device_identity=ident,
        )

    def test_is_connected_initially_false(self):
        client = self._make_client()
        assert client.is_connected is False

    def test_on_command_registers_handler(self):
        client = self._make_client()

        @client.on_command("ping")
        async def handler(cmd):
            pass

        assert "ping" in client._handlers

    def test_on_command_decorator_returns_original_function(self):
        client = self._make_client()

        async def my_handler(cmd):
            return "ok"

        result = client.on_command("test")(my_handler)
        assert result is my_handler

    def test_multiple_handlers(self):
        client = self._make_client()

        @client.on_command("alpha")
        async def h_alpha(cmd): pass

        @client.on_command("beta")
        async def h_beta(cmd): pass

        assert "alpha" in client._handlers
        assert "beta" in client._handlers


# ---------------------------------------------------------------------------
# HealthSnapshot
# ---------------------------------------------------------------------------

class TestHealthSnapshot:
    def _make_snapshot(self, status="healthy", errors=None):
        return HealthSnapshot(
            node_id="test-node-id",
            timestamp=1234567890.0,
            status=status,
            uptime=42.0,
            peer_count=3,
            task_count=1,
            system=SystemMetrics(cpu_count=4, uptime_seconds=100.0, python_version="3.11"),
            errors=errors or [],
        )

    def test_to_dict_has_expected_keys(self):
        snap = self._make_snapshot()
        d = snap.to_dict()
        for key in ("node_id", "timestamp", "status", "uptime",
                    "peer_count", "task_count", "system", "errors"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_system_is_dict(self):
        snap = self._make_snapshot()
        assert isinstance(snap.to_dict()["system"], dict)


# ---------------------------------------------------------------------------
# HealthReporter
# ---------------------------------------------------------------------------

class TestHealthReporter:
    def test_snapshot_healthy_with_no_errors(self):
        reporter = HealthReporter(node_id="node-abc")
        snap = reporter.snapshot()
        assert snap.status == "healthy"
        assert snap.errors == []

    def test_snapshot_degraded_with_two_errors(self):
        reporter = HealthReporter(node_id="node-abc")
        snap = reporter.snapshot(errors=["err1", "err2"])
        assert snap.status == "degraded"
        assert len(snap.errors) == 2

    def test_snapshot_unhealthy_with_three_errors(self):
        reporter = HealthReporter(node_id="node-abc")
        snap = reporter.snapshot(errors=["e1", "e2", "e3"])
        assert snap.status == "unhealthy"

    def test_snapshot_node_id_matches(self):
        reporter = HealthReporter(node_id="my-node")
        snap = reporter.snapshot()
        assert snap.node_id == "my-node"
