"""
AIM Gateway — edge-facing entry point into the AIM mesh backbone.

Gateway nodes sit at the boundary between thin edge clients (phones, home
devices, web-bridge sessions) and the relay backbone.  They:

* Accept inbound TCP connections from edge nodes.
* Authenticate the ``CreatorSignature`` on every incoming message.
* Forward messages into the relay layer using a healthy-relay pool.
* Route relay responses back to the originating edge connection.
* Perform periodic heartbeats to every configured relay; failed relays are
  excluded from routing until they recover.
"""

from aim.gateway.node import GatewayNode

__all__ = ["GatewayNode"]
