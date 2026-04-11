"""Tests for the AIM Virtual Cloud (vcloud) layer."""

from __future__ import annotations

import pytest

from aim.vcloud.resource import (
    ResourceKind,
    ResourceState,
    VirtualCPU,
    VirtualServer,
    VCloud,
)
from aim.vcloud.manager import VCloudManager
from aim.node.registry import NodeRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_manager() -> VCloudManager:
    return VCloudManager(registry=NodeRegistry())


# ---------------------------------------------------------------------------
# VirtualCPU
# ---------------------------------------------------------------------------

class TestVirtualCPU:
    def test_kind_is_vcpu(self):
        v = VirtualCPU(kind=ResourceKind.VCPU, cores=2, clock_mhz=2000)
        assert v.kind == ResourceKind.VCPU

    def test_default_state_available(self):
        v = VirtualCPU(kind=ResourceKind.VCPU)
        assert v.state == ResourceState.AVAILABLE

    def test_allocate(self):
        v = VirtualCPU(kind=ResourceKind.VCPU)
        v.allocate()
        assert v.state == ResourceState.ALLOCATED

    def test_allocate_twice_raises(self):
        v = VirtualCPU(kind=ResourceKind.VCPU)
        v.allocate()
        with pytest.raises(RuntimeError, match="cannot be allocated"):
            v.allocate()

    def test_release(self):
        v = VirtualCPU(kind=ResourceKind.VCPU)
        v.allocate()
        v.release()
        assert v.state == ResourceState.AVAILABLE

    def test_suspend(self):
        v = VirtualCPU(kind=ResourceKind.VCPU)
        v.suspend()
        assert v.state == ResourceState.SUSPENDED

    def test_destroy(self):
        v = VirtualCPU(kind=ResourceKind.VCPU)
        v.destroy()
        assert v.state == ResourceState.DESTROYED

    def test_release_after_destroy_raises(self):
        v = VirtualCPU(kind=ResourceKind.VCPU)
        v.destroy()
        with pytest.raises(RuntimeError, match="destroyed"):
            v.release()

    def test_cores_must_be_positive(self):
        with pytest.raises(ValueError, match="at least 1 core"):
            VirtualCPU(kind=ResourceKind.VCPU, cores=0)

    def test_clock_mhz_must_be_positive(self):
        with pytest.raises(ValueError, match="clock_mhz"):
            VirtualCPU(kind=ResourceKind.VCPU, clock_mhz=0)

    def test_to_dict_contains_cores(self):
        v = VirtualCPU(kind=ResourceKind.VCPU, cores=4, clock_mhz=3000)
        d = v.to_dict()
        assert d["cores"] == 4
        assert d["clock_mhz"] == 3000
        assert d["kind"] == "vcpu"

    def test_creator_default(self):
        from aim.identity.signature import ORIGIN_CREATOR
        v = VirtualCPU(kind=ResourceKind.VCPU)
        assert v.creator == ORIGIN_CREATOR


# ---------------------------------------------------------------------------
# VirtualServer
# ---------------------------------------------------------------------------

class TestVirtualServer:
    def test_kind_is_vserver(self):
        vs = VirtualServer(kind=ResourceKind.VSERVER)
        assert vs.kind == ResourceKind.VSERVER

    def test_defaults(self):
        vs = VirtualServer(kind=ResourceKind.VSERVER)
        assert vs.vcpu_count == 1
        assert vs.memory_mb == 512
        assert vs.state == ResourceState.AVAILABLE

    def test_vcpu_count_validation(self):
        with pytest.raises(ValueError, match="at least 1 vCPU"):
            VirtualServer(kind=ResourceKind.VSERVER, vcpu_count=0)

    def test_memory_validation(self):
        with pytest.raises(ValueError, match="memory_mb"):
            VirtualServer(kind=ResourceKind.VSERVER, memory_mb=0)

    def test_to_dict_contains_vcpu_and_memory(self):
        vs = VirtualServer(kind=ResourceKind.VSERVER, vcpu_count=2, memory_mb=1024,
                           host="10.0.0.1", port=7700)
        d = vs.to_dict()
        assert d["vcpu_count"] == 2
        assert d["memory_mb"] == 1024
        assert d["host"] == "10.0.0.1"
        assert d["port"] == 7700
        assert d["kind"] == "vserver"


# ---------------------------------------------------------------------------
# VCloud
# ---------------------------------------------------------------------------

class TestVCloud:
    def test_kind_is_vcloud(self):
        vc = VCloud(kind=ResourceKind.VCLOUD)
        assert vc.kind == ResourceKind.VCLOUD

    def test_add_server(self):
        vc = VCloud(kind=ResourceKind.VCLOUD)
        vc.add_server("srv-1")
        vc.add_server("srv-2")
        assert "srv-1" in vc.servers
        assert "srv-2" in vc.servers

    def test_add_server_idempotent(self):
        vc = VCloud(kind=ResourceKind.VCLOUD)
        vc.add_server("srv-1")
        vc.add_server("srv-1")
        assert vc.servers.count("srv-1") == 1

    def test_remove_server(self):
        vc = VCloud(kind=ResourceKind.VCLOUD)
        vc.add_server("srv-1")
        vc.remove_server("srv-1")
        assert "srv-1" not in vc.servers

    def test_to_dict_contains_region_and_servers(self):
        vc = VCloud(kind=ResourceKind.VCLOUD, region="us-east")
        vc.add_server("srv-1")
        d = vc.to_dict()
        assert d["region"] == "us-east"
        assert "srv-1" in d["servers"]
        assert d["kind"] == "vcloud"


# ---------------------------------------------------------------------------
# VCloudManager
# ---------------------------------------------------------------------------

class TestVCloudManager:
    def setup_method(self):
        self.mgr = _fresh_manager()

    def test_create_vcpu(self):
        v = self.mgr.create_vcpu(name="test-cpu", cores=4)
        assert v.cores == 4
        assert self.mgr.get(v.resource_id) is v

    def test_create_vserver(self):
        vs = self.mgr.create_vserver(name="my-server", vcpu_count=2, memory_mb=1024)
        assert vs.vcpu_count == 2
        assert vs.memory_mb == 1024
        assert self.mgr.get(vs.resource_id) is vs

    def test_create_vserver_registers_node_when_port_given(self):
        registry = NodeRegistry()
        mgr = VCloudManager(registry=registry)
        vs = mgr.create_vserver(name="srv", port=9900)
        record = registry.get(vs.node_id)
        assert record is not None
        assert record.port == 9900
        assert "vserver" in record.capabilities

    def test_create_vserver_no_port_no_registry(self):
        registry = NodeRegistry()
        mgr = VCloudManager(registry=registry)
        vs = mgr.create_vserver(name="unbound")  # port=0
        assert registry.count() == 0
        assert vs.port == 0

    def test_create_vcloud(self):
        vc = self.mgr.create_vcloud(name="my-cloud", region="eu-west")
        assert vc.region == "eu-west"
        assert self.mgr.get(vc.resource_id) is vc

    def test_allocate(self):
        v = self.mgr.create_vcpu()
        self.mgr.allocate(v.resource_id)
        assert v.state == ResourceState.ALLOCATED

    def test_release(self):
        v = self.mgr.create_vcpu()
        self.mgr.allocate(v.resource_id)
        self.mgr.release(v.resource_id)
        assert v.state == ResourceState.AVAILABLE

    def test_suspend(self):
        v = self.mgr.create_vcpu()
        self.mgr.suspend(v.resource_id)
        assert v.state == ResourceState.SUSPENDED

    def test_destroy_removes_resource(self):
        v = self.mgr.create_vcpu()
        rid = v.resource_id
        self.mgr.destroy(rid)
        assert self.mgr.get(rid) is None

    def test_destroy_deregisters_vserver(self):
        registry = NodeRegistry()
        mgr = VCloudManager(registry=registry)
        vs = mgr.create_vserver(name="srv", port=9901)
        assert registry.count() == 1
        mgr.destroy(vs.resource_id)
        assert registry.count() == 0

    def test_allocate_nonexistent_raises(self):
        with pytest.raises(KeyError):
            self.mgr.allocate("nonexistent-id")

    def test_release_nonexistent_raises(self):
        with pytest.raises(KeyError):
            self.mgr.release("nonexistent-id")

    def test_by_kind(self):
        self.mgr.create_vcpu()
        self.mgr.create_vcpu()
        self.mgr.create_vserver()
        assert len(self.mgr.by_kind(ResourceKind.VCPU)) == 2
        assert len(self.mgr.by_kind(ResourceKind.VSERVER)) == 1

    def test_by_state(self):
        v1 = self.mgr.create_vcpu()
        v2 = self.mgr.create_vcpu()
        self.mgr.allocate(v1.resource_id)
        available = self.mgr.by_state(ResourceState.AVAILABLE)
        allocated = self.mgr.by_state(ResourceState.ALLOCATED)
        assert v2 in available
        assert v1 in allocated

    def test_snapshot(self):
        self.mgr.create_vcpu()
        self.mgr.create_vserver()
        self.mgr.create_vcloud()
        snap = self.mgr.snapshot()
        assert snap["total"] == 3
        assert snap["vcpus"] == 1
        assert snap["vservers"] == 1
        assert snap["vclouds"] == 1
        assert len(snap["resources"]) == 3

    def test_count(self):
        assert self.mgr.count() == 0
        self.mgr.create_vcpu()
        assert self.mgr.count() == 1

    def test_all_resources(self):
        self.mgr.create_vcpu()
        self.mgr.create_vserver()
        assert len(self.mgr.all_resources()) == 2

    def test_default_singleton(self):
        # Two calls to default() return the same instance
        a = VCloudManager.default()
        b = VCloudManager.default()
        assert a is b
