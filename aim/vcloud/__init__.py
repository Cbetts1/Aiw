"""
AIM Virtual Cloud — virtual compute resources (vCPU, vServer, vCloud).

Provides lightweight, mesh-aware virtual resource abstractions that let AIM
nodes advertise and schedule logical compute allocations across the mesh.
"""

from aim.vcloud.resource import (
    ResourceKind,
    ResourceState,
    VirtualResource,
    VirtualCPU,
    VirtualServer,
    VCloud,
)
from aim.vcloud.manager import VCloudManager

__all__ = [
    "ResourceKind",
    "ResourceState",
    "VirtualResource",
    "VirtualCPU",
    "VirtualServer",
    "VCloud",
    "VCloudManager",
]
