"""
AIM DNS Bridge — standard DNS ↔ ANS name translation.

Provides the ``DNSBridge`` that makes AIM ``aim://`` names reachable from
the conventional web and vice versa.
"""

from aim.dns.bridge import DNSBridge, BridgeResult

__all__ = ["DNSBridge", "BridgeResult"]
