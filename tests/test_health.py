"""Tests for the AIM Health module."""

from __future__ import annotations

import json

import pytest

from aim.health.metrics import SystemMetrics
from aim.health.reporter import HealthReporter, HealthSnapshot


# ---------------------------------------------------------------------------
# SystemMetrics
# ---------------------------------------------------------------------------

class TestSystemMetrics:
    def test_collect_returns_valid_metrics(self):
        metrics = SystemMetrics.collect()
        assert isinstance(metrics.cpu_count, int)
        assert metrics.cpu_count >= 1
        assert isinstance(metrics.uptime_seconds, float)
        assert metrics.uptime_seconds >= 0.0
        assert isinstance(metrics.python_version, str)
        assert len(metrics.python_version) > 0

    def test_to_dict_has_expected_keys(self):
        metrics = SystemMetrics.collect()
        d = metrics.to_dict()
        assert "cpu_count" in d
        assert "uptime_seconds" in d
        assert "python_version" in d

    def test_to_dict_types(self):
        metrics = SystemMetrics.collect()
        d = metrics.to_dict()
        assert isinstance(d["cpu_count"], int)
        assert isinstance(d["uptime_seconds"], float)
        assert isinstance(d["python_version"], str)


# ---------------------------------------------------------------------------
# HealthReporter
# ---------------------------------------------------------------------------

class TestHealthReporter:
    def test_snapshot_default_is_healthy(self):
        reporter = HealthReporter(node_id="test-node")
        snap = reporter.snapshot()
        assert snap.status == "healthy"
        assert snap.node_id == "test-node"

    def test_snapshot_with_peer_and_task_counts(self):
        reporter = HealthReporter(node_id="test-node")
        snap = reporter.snapshot(peer_count=5, task_count=3)
        assert snap.peer_count == 5
        assert snap.task_count == 3

    def test_snapshot_uptime_is_positive(self):
        reporter = HealthReporter(node_id="test-node")
        snap = reporter.snapshot()
        assert snap.uptime >= 0.0

    def test_snapshot_system_metrics_present(self):
        reporter = HealthReporter(node_id="test-node")
        snap = reporter.snapshot()
        assert isinstance(snap.system, SystemMetrics)

    def test_to_http_response_200_for_healthy(self):
        reporter = HealthReporter(node_id="test-node")
        snap = reporter.snapshot()
        code, body = HealthReporter.to_http_response(snap)
        assert code == 200

    def test_to_http_response_200_for_degraded(self):
        reporter = HealthReporter(node_id="test-node")
        snap = reporter.snapshot(errors=["minor issue"])
        code, body = HealthReporter.to_http_response(snap)
        assert code == 200

    def test_to_http_response_503_for_unhealthy(self):
        reporter = HealthReporter(node_id="test-node")
        snap = reporter.snapshot(errors=["e1", "e2", "e3"])
        code, body = HealthReporter.to_http_response(snap)
        assert code == 503


# ---------------------------------------------------------------------------
# HealthSnapshot
# ---------------------------------------------------------------------------

class TestHealthSnapshot:
    def _make_snap(self, status="healthy", errors=None):
        metrics = SystemMetrics(cpu_count=2, uptime_seconds=500.0, python_version="3.11")
        return HealthSnapshot(
            node_id="snap-node",
            timestamp=9999.9,
            status=status,
            uptime=30.0,
            peer_count=1,
            task_count=0,
            system=metrics,
            errors=errors or [],
        )

    def test_to_json_is_valid_json(self):
        snap = self._make_snap()
        raw = snap.to_json()
        parsed = json.loads(raw)
        assert parsed["node_id"] == "snap-node"
        assert parsed["status"] == "healthy"

    def test_to_json_contains_system(self):
        snap = self._make_snap()
        parsed = json.loads(snap.to_json())
        assert "system" in parsed
        assert parsed["system"]["cpu_count"] == 2

    def test_to_dict_errors_preserved(self):
        snap = self._make_snap(status="degraded", errors=["disk full"])
        d = snap.to_dict()
        assert "disk full" in d["errors"]
