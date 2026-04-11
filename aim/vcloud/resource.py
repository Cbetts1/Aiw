"""
AIM Virtual Cloud — virtual compute resource definitions.

VirtualCPU, VirtualServer, and VCloud are dataclass-based virtual resources.
They model logical compute allocations within the AIM mesh so that nodes
can advertise, schedule, and track compute work without OS-level isolation.

Classes
-------
ResourceKind    : Enum of resource types (vcpu, vserver, vcloud).
ResourceState   : Lifecycle states (available, allocated, suspended, destroyed).
VirtualResource : Abstract base with common fields and lifecycle methods.
VirtualCPU      : A virtual CPU unit (cores + clock speed).
VirtualServer   : A virtual server (vCPUs + memory + optional AIM node binding).
VCloud          : A named collection of VirtualServers in a logical region.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from aim.identity.signature import ORIGIN_CREATOR


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ResourceKind(str, Enum):
    """The type of a virtual compute resource."""
    VCPU    = "vcpu"
    VSERVER = "vserver"
    VCLOUD  = "vcloud"


class ResourceState(str, Enum):
    """Lifecycle state of a virtual resource."""
    AVAILABLE = "available"
    ALLOCATED = "allocated"
    SUSPENDED = "suspended"
    DESTROYED = "destroyed"


# ---------------------------------------------------------------------------
# Base resource
# ---------------------------------------------------------------------------

@dataclass
class VirtualResource:
    """
    Base class for all virtual compute resources in the AIM mesh.

    Parameters
    ----------
    kind:        Type of resource (set by subclasses).
    resource_id: Unique identifier (auto-generated UUID if not provided).
    name:        Human-readable name.
    state:       Current lifecycle state.
    creator:     Origin-creator identifier propagated from the mesh.
    created_at:  Unix epoch timestamp of creation.
    metadata:    Arbitrary key-value store for additional attributes.
    """

    kind:        ResourceKind
    resource_id: str            = field(default_factory=lambda: str(uuid.uuid4()))
    name:        str            = ""
    state:       ResourceState  = ResourceState.AVAILABLE
    creator:     str            = ORIGIN_CREATOR
    created_at:  float          = field(default_factory=time.time)
    metadata:    dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def allocate(self) -> None:
        """Transition from AVAILABLE → ALLOCATED."""
        if self.state != ResourceState.AVAILABLE:
            raise RuntimeError(
                f"Resource {self.resource_id!r} cannot be allocated "
                f"(current state: {self.state.value})"
            )
        self.state = ResourceState.ALLOCATED

    def release(self) -> None:
        """Transition from ALLOCATED or SUSPENDED → AVAILABLE."""
        if self.state == ResourceState.DESTROYED:
            raise RuntimeError(f"Resource {self.resource_id!r} has been destroyed")
        self.state = ResourceState.AVAILABLE

    def suspend(self) -> None:
        """Transition from AVAILABLE or ALLOCATED → SUSPENDED."""
        if self.state not in (ResourceState.ALLOCATED, ResourceState.AVAILABLE):
            raise RuntimeError(
                f"Resource {self.resource_id!r} cannot be suspended "
                f"(current state: {self.state.value})"
            )
        self.state = ResourceState.SUSPENDED

    def destroy(self) -> None:
        """Mark as DESTROYED (terminal state)."""
        self.state = ResourceState.DESTROYED

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind":        self.kind.value,
            "resource_id": self.resource_id,
            "name":        self.name,
            "state":       self.state.value,
            "creator":     self.creator,
            "created_at":  self.created_at,
            "metadata":    dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# VirtualCPU
# ---------------------------------------------------------------------------

@dataclass
class VirtualCPU(VirtualResource):
    """
    A virtual CPU resource — a logical compute unit.

    Parameters
    ----------
    cores:     Number of virtual CPU cores (minimum 1).
    clock_mhz: Clock speed in MHz (minimum 1).
    """

    cores:     int = 1
    clock_mhz: int = 1000

    def __post_init__(self) -> None:
        self.kind = ResourceKind.VCPU
        if self.cores < 1:
            raise ValueError("VirtualCPU must have at least 1 core")
        if self.clock_mhz < 1:
            raise ValueError("VirtualCPU clock_mhz must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["cores"] = self.cores
        d["clock_mhz"] = self.clock_mhz
        return d


# ---------------------------------------------------------------------------
# VirtualServer
# ---------------------------------------------------------------------------

@dataclass
class VirtualServer(VirtualResource):
    """
    A virtual server — bundles vCPUs and memory, optionally bound to an AIM node.

    Parameters
    ----------
    vcpu_count: Number of virtual CPUs allocated to this server.
    memory_mb:  Amount of virtual memory in megabytes.
    node_id:    AIM node_id this server maps to (empty if unbound).
    host:       Network host for the AIM node bound to this server.
    port:       Network port for the AIM node (0 if unbound).
    """

    vcpu_count: int = 1
    memory_mb:  int = 512
    node_id:    str = ""
    host:       str = "127.0.0.1"
    port:       int = 0

    def __post_init__(self) -> None:
        self.kind = ResourceKind.VSERVER
        if self.vcpu_count < 1:
            raise ValueError("VirtualServer must have at least 1 vCPU")
        if self.memory_mb < 1:
            raise ValueError("VirtualServer memory_mb must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["vcpu_count"] = self.vcpu_count
        d["memory_mb"]  = self.memory_mb
        d["node_id"]    = self.node_id
        d["host"]       = self.host
        d["port"]       = self.port
        return d


# ---------------------------------------------------------------------------
# VCloud
# ---------------------------------------------------------------------------

@dataclass
class VCloud(VirtualResource):
    """
    A virtual cloud — a named, logical grouping of VirtualServers.

    Parameters
    ----------
    region:  Logical region identifier (e.g. ``"us-east"``, ``"local"``).
    servers: List of ``VirtualServer.resource_id`` values in this cloud.
    """

    region:  str        = "local"
    servers: list[str]  = field(default_factory=list)

    def __post_init__(self) -> None:
        self.kind = ResourceKind.VCLOUD

    def add_server(self, server_id: str) -> None:
        """Add a VirtualServer by resource_id (idempotent)."""
        if server_id not in self.servers:
            self.servers.append(server_id)

    def remove_server(self, server_id: str) -> None:
        """Remove a VirtualServer from this cloud by resource_id."""
        self.servers = [s for s in self.servers if s != server_id]

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["region"]  = self.region
        d["servers"] = list(self.servers)
        return d
