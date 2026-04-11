"""
AIM VCloudManager — allocates and tracks virtual compute resources.

The ``VCloudManager`` is a thread-safe coordinator layer that:
- Creates ``VirtualCPU``, ``VirtualServer``, and ``VCloud`` instances.
- Tracks all live resources in memory.
- Auto-registers ``VirtualServer`` instances with the ``NodeRegistry`` so
  that the task router can discover them as capable nodes.
- Exposes JSON-serialisable snapshots for the web API.

A single shared instance is available via ``VCloudManager.default()``.
"""

from __future__ import annotations

import threading
from typing import Any

from aim.vcloud.resource import (
    ResourceKind,
    ResourceState,
    VirtualResource,
    VirtualCPU,
    VirtualServer,
    VCloud,
)
from aim.node.registry import NodeRegistry, NodeRecord
from aim.identity.signature import ORIGIN_CREATOR


class VCloudManager:
    """
    Thread-safe virtual cloud resource manager.

    Parameters
    ----------
    registry:
        The ``NodeRegistry`` used to auto-register VirtualServers.
        Defaults to the global singleton.
    """

    _default: "VCloudManager | None" = None
    _class_lock = threading.Lock()

    def __init__(self, registry: NodeRegistry | None = None) -> None:
        self._resources: dict[str, VirtualResource] = {}
        self._lock = threading.RLock()
        self._registry = registry or NodeRegistry.default()

    @classmethod
    def default(cls) -> "VCloudManager":
        """Return the process-global singleton VCloudManager."""
        with cls._class_lock:
            if cls._default is None:
                cls._default = cls()
            return cls._default

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    def create_vcpu(
        self,
        name: str = "",
        cores: int = 1,
        clock_mhz: int = 1000,
        creator: str = ORIGIN_CREATOR,
        metadata: dict[str, Any] | None = None,
    ) -> VirtualCPU:
        """
        Create and track a new VirtualCPU.

        Parameters
        ----------
        name:      Human-readable name (auto-generated if empty).
        cores:     Number of virtual cores.
        clock_mhz: Clock speed in MHz.
        creator:   Origin-creator identifier.
        metadata:  Additional metadata.

        Returns
        -------
        VirtualCPU
        """
        vcpu = VirtualCPU(
            kind=ResourceKind.VCPU,
            name=name or f"vcpu-{cores}core-{clock_mhz}mhz",
            cores=cores,
            clock_mhz=clock_mhz,
            creator=creator,
            metadata=metadata or {},
        )
        with self._lock:
            self._resources[vcpu.resource_id] = vcpu
        return vcpu

    def create_vserver(
        self,
        name: str = "",
        vcpu_count: int = 1,
        memory_mb: int = 512,
        host: str = "127.0.0.1",
        port: int = 0,
        node_id: str = "",
        creator: str = ORIGIN_CREATOR,
        metadata: dict[str, Any] | None = None,
    ) -> VirtualServer:
        """
        Create and track a new VirtualServer.

        If *port* is non-zero the server is automatically registered with the
        ``NodeRegistry`` so the task router can dispatch work to it.

        Parameters
        ----------
        name:       Human-readable name (auto-generated if empty).
        vcpu_count: Number of virtual CPUs.
        memory_mb:  Memory allocation in megabytes.
        host:       Hostname or IP for the bound AIM node.
        port:       TCP port for the bound AIM node (0 = unbound).
        node_id:    AIM node UUID to bind (auto-uses resource_id if empty).
        creator:    Origin-creator identifier.
        metadata:   Additional metadata.

        Returns
        -------
        VirtualServer
        """
        vs = VirtualServer(
            kind=ResourceKind.VSERVER,
            name=name or f"vserver-{vcpu_count}cpu-{memory_mb}mb",
            vcpu_count=vcpu_count,
            memory_mb=memory_mb,
            host=host,
            port=port,
            node_id=node_id,
            creator=creator,
            metadata=metadata or {},
        )
        # If node_id not supplied, use the resource_id as the node identity
        if not vs.node_id:
            vs.node_id = vs.resource_id

        with self._lock:
            self._resources[vs.resource_id] = vs

        # Auto-register in NodeRegistry when port is given
        if port:
            self._registry.register(NodeRecord(
                node_id=vs.node_id,
                host=host,
                port=port,
                capabilities=["vserver", "compute"],
                creator=creator,
                metadata={
                    "vserver_name": vs.name,
                    "vcpu_count":   vcpu_count,
                    "memory_mb":    memory_mb,
                    "resource_id":  vs.resource_id,
                },
            ))
        return vs

    def create_vcloud(
        self,
        name: str = "",
        region: str = "local",
        creator: str = ORIGIN_CREATOR,
        metadata: dict[str, Any] | None = None,
    ) -> VCloud:
        """
        Create and track a new VCloud.

        Parameters
        ----------
        name:    Human-readable name (auto-generated if empty).
        region:  Logical region identifier.
        creator: Origin-creator identifier.
        metadata: Additional metadata.

        Returns
        -------
        VCloud
        """
        vc = VCloud(
            kind=ResourceKind.VCLOUD,
            name=name or f"vcloud-{region}",
            region=region,
            creator=creator,
            metadata=metadata or {},
        )
        with self._lock:
            self._resources[vc.resource_id] = vc
        return vc

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get(self, resource_id: str) -> VirtualResource | None:
        """Return a resource by its ID, or None."""
        with self._lock:
            return self._resources.get(resource_id)

    def all_resources(self) -> list[VirtualResource]:
        """Return all tracked resources."""
        with self._lock:
            return list(self._resources.values())

    def by_kind(self, kind: ResourceKind) -> list[VirtualResource]:
        """Return all resources of the given kind."""
        with self._lock:
            return [r for r in self._resources.values() if r.kind == kind]

    def by_state(self, state: ResourceState) -> list[VirtualResource]:
        """Return all resources in the given state."""
        with self._lock:
            return [r for r in self._resources.values() if r.state == state]

    def count(self) -> int:
        with self._lock:
            return len(self._resources)

    # ------------------------------------------------------------------
    # Lifecycle operations
    # ------------------------------------------------------------------

    def allocate(self, resource_id: str) -> VirtualResource:
        """Mark a resource as ALLOCATED.  Raises KeyError if not found."""
        with self._lock:
            r = self._resources.get(resource_id)
            if r is None:
                raise KeyError(f"Resource {resource_id!r} not found")
            r.allocate()
            return r

    def release(self, resource_id: str) -> VirtualResource:
        """Release a resource back to AVAILABLE.  Raises KeyError if not found."""
        with self._lock:
            r = self._resources.get(resource_id)
            if r is None:
                raise KeyError(f"Resource {resource_id!r} not found")
            r.release()
            return r

    def suspend(self, resource_id: str) -> VirtualResource:
        """Suspend a resource.  Raises KeyError if not found."""
        with self._lock:
            r = self._resources.get(resource_id)
            if r is None:
                raise KeyError(f"Resource {resource_id!r} not found")
            r.suspend()
            return r

    def destroy(self, resource_id: str) -> None:
        """
        Destroy and remove a resource.

        The resource is marked DESTROYED, removed from the internal store,
        and deregistered from the NodeRegistry (for VirtualServers).
        """
        with self._lock:
            r = self._resources.get(resource_id)
            if r is None:
                return
            r.destroy()
            del self._resources[resource_id]

        # Deregister VirtualServer node_id from NodeRegistry
        if isinstance(r, VirtualServer) and r.node_id:
            self._registry.deregister(r.node_id)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serialisable summary of all managed resources."""
        resources = self.all_resources()
        vcpus    = [r for r in resources if r.kind == ResourceKind.VCPU]
        vservers = [r for r in resources if r.kind == ResourceKind.VSERVER]
        vclouds  = [r for r in resources if r.kind == ResourceKind.VCLOUD]
        return {
            "total":     len(resources),
            "vcpus":     len(vcpus),
            "vservers":  len(vservers),
            "vclouds":   len(vclouds),
            "resources": [r.to_dict() for r in resources],
            "creator":   ORIGIN_CREATOR,
        }
