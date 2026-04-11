"""
AIM Relay — backbone nodes that keep the mesh self-sustaining and routable.

A relay node acts as an intermediate hop between nodes that cannot communicate
directly, providing forwarding, health-based discovery, and optional caching.

Exports
-------
RelayNode     : a specialised BaseNode that forwards AIM messages
RelayRegistry : tracks relay nodes and their health status
RelayRecord   : metadata record for a single relay
"""

from .node import RelayNode
from .registry import RelayRegistry, RelayRecord

__all__ = ["RelayNode", "RelayRegistry", "RelayRecord"]
