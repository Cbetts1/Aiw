"""
AIM DNS Bridge — standard DNS ↔ ANS name-translation layer.

The DNS Bridge is the glue between the classical internet (DNS/HTTP) and the
AIM mesh (ANS/AIM protocol).  It provides:

1. ``resolve(name)``
   Resolve any hostname or ANS name by trying the ANS registry first, then
   falling back to a system DNS lookup.  Returns a ``BridgeResult``.

2. ``register_from_dns(hostname, node_id, port, …)``
   Take a classical DNS hostname and anchor it as an ANS record so AIM nodes
   can reach it by an ``aim://`` URI.

3. ``aim_to_dns(aim_uri)``
   Derive a conventional hostname from an ``aim://`` URI.

4. ``dns_to_aim(hostname)``
   Derive an ``aim://`` URI from a conventional hostname.

The bridge uses ``ANSRegistry`` as its source of truth for ANS operations,
making it safe to call from multiple threads and coroutines.
"""

from __future__ import annotations

import socket
import logging
from dataclasses import dataclass, field
from typing import Any

from aim.ans.registry import ANSRegistry, ANSRecord
from aim.ans.resolver import ANSResolver
from aim.identity.signature import ORIGIN_CREATOR

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class BridgeResult:
    """
    The result of a DNS Bridge name resolution.

    Attributes
    ----------
    name:         The canonical name that was resolved.
    host:         IP address or hostname of the resolved target.
    port:         Port number (0 when resolved from DNS with no port info).
    node_id:      AIM node UUID (empty string for DNS-only results).
    aim_uri:      Canonical ``aim://`` URI (empty string for DNS-only results).
    source:       ``"ans"`` if resolved via ANS, ``"dns"`` otherwise.
    capabilities: Capability tags from the AIM node (empty for DNS-only).
    """

    name:         str
    host:         str
    port:         int
    node_id:      str       = ""
    aim_uri:      str       = ""
    source:       str       = "dns"
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name":         self.name,
            "host":         self.host,
            "port":         self.port,
            "node_id":      self.node_id,
            "aim_uri":      self.aim_uri,
            "source":       self.source,
            "capabilities": list(self.capabilities),
        }


# ---------------------------------------------------------------------------
# DNSBridge
# ---------------------------------------------------------------------------

class DNSBridge:
    """
    Standard DNS ↔ ANS name-translation bridge.

    Parameters
    ----------
    registry:
        The ``ANSRegistry`` used for ANS lookups and registrations.
        Defaults to the global singleton.
    dns_timeout:
        Timeout in seconds for system DNS lookups (default: 3.0).
    """

    def __init__(
        self,
        registry: ANSRegistry | None = None,
        dns_timeout: float = 3.0,
    ) -> None:
        self._registry    = registry or ANSRegistry.default()
        self._resolver    = ANSResolver(self._registry)
        self._dns_timeout = dns_timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, name: str, default_port: int = 7700) -> BridgeResult | None:
        """
        Resolve *name* to a ``BridgeResult``.

        Resolution order:
        1. If the name looks like an ANS name (``aim://`` prefix **or** a
           bare name ending in ``.aim``), try the ANS registry first.
        2. Fall back to a system DNS lookup for conventional hostnames.

        Parameters
        ----------
        name:
            Any of the following forms:

            - ``aim://weather.public.aim``   — canonical ANS URI
            - ``weather.public.aim``         — bare ANS name
            - ``example.com``               — conventional DNS hostname

        default_port:
            Port to use when the result comes from DNS only.

        Returns
        -------
        BridgeResult | None
            ``None`` if the name cannot be resolved by either ANS or DNS.
        """
        # --- ANS path ---
        aim_name = self._to_ans_name(name)
        if aim_name is not None:
            node = self._resolver.resolve(aim_name)
            if node is not None:
                return BridgeResult(
                    name=aim_name,
                    host=node.host,
                    port=node.port,
                    node_id=node.node_id,
                    aim_uri=f"aim://{aim_name}",
                    source="ans",
                    capabilities=list(node.capabilities),
                )

        # --- DNS fallback ---
        hostname = self._strip_aim_scheme(name)
        try:
            socket.setdefaulttimeout(self._dns_timeout)
            info = socket.getaddrinfo(
                hostname, None, socket.AF_INET, socket.SOCK_STREAM
            )
            host = info[0][4][0]
            return BridgeResult(
                name=hostname,
                host=host,
                port=default_port,
                source="dns",
            )
        except (socket.gaierror, OSError) as exc:
            logger.debug("DNS lookup failed for %r: %s", hostname, exc)
            return None
        finally:
            socket.setdefaulttimeout(None)

    def register_from_dns(
        self,
        hostname: str,
        node_id: str,
        port: int,
        capabilities: list[str] | None = None,
        creator: str = ORIGIN_CREATOR,
        ttl_seconds: int = 3600,
    ) -> ANSRecord:
        """
        Derive an ANS name from a classical DNS *hostname* and register it.

        The derived ANS name is ``<hostname>.aim`` unless the hostname already
        ends with ``.aim``.  The bridge attempts a live DNS lookup to resolve
        the hostname to an IP; if the lookup fails, the hostname is used
        verbatim as the AIM node address.

        Parameters
        ----------
        hostname:    Classical hostname (e.g. ``weather.example.com``).
        node_id:     AIM node UUID to associate with this name.
        port:        TCP port the AIM node listens on.
        capabilities: Capability tags to advertise.
        creator:     Origin-creator identifier.
        ttl_seconds: Cache TTL for the ANS record.

        Returns
        -------
        ANSRecord
            The newly registered record.
        """
        aim_uri  = self.dns_to_aim(hostname)
        bare     = aim_uri[6:] if aim_uri.startswith("aim://") else aim_uri

        # Attempt live DNS resolution for the actual IP
        try:
            socket.setdefaulttimeout(self._dns_timeout)
            info = socket.getaddrinfo(
                hostname, None, socket.AF_INET, socket.SOCK_STREAM
            )
            ip = info[0][4][0]
        except (socket.gaierror, OSError):
            ip = hostname   # use hostname as-is if DNS is unavailable
        finally:
            socket.setdefaulttimeout(None)

        record = ANSRecord(
            name=bare,
            node_id=node_id,
            host=ip,
            port=port,
            capabilities=capabilities or [],
            creator=creator,
            ttl_seconds=ttl_seconds,
        )
        self._registry.register(record)
        logger.info(
            "DNS Bridge: registered %r → %s:%s (node_id=%s)",
            bare, ip, port, node_id[:8],
        )
        return record

    @staticmethod
    def aim_to_dns(aim_uri: str) -> str:
        """
        Derive a conventional hostname from an ``aim://`` URI.

        ``aim://weather.public.aim``  →  ``weather.public.aim``

        The ``.aim`` TLD is reserved for the AIM mesh.  For public internet
        DNS, operators typically serve it under a delegated zone such as
        ``weather.public.aim.foundationhomepage.org``.  This method returns
        the bare label-dotted name; callers can apply their own suffix.
        """
        if aim_uri.startswith("aim://"):
            return aim_uri[6:]
        return aim_uri

    @staticmethod
    def dns_to_aim(hostname: str) -> str:
        """
        Derive an ``aim://`` URI from a conventional DNS *hostname*.

        If the hostname already ends with ``.aim`` it is used as-is.
        Otherwise ``.aim`` is appended as the TLD.

        Examples
        --------
        ``weather.example.com``  →  ``aim://weather.example.com.aim``
        ``weather.public.aim``   →  ``aim://weather.public.aim``
        """
        bare = hostname.strip().lower()
        if not bare.endswith(".aim"):
            bare = bare + ".aim"
        return f"aim://{bare}"

    def list_ans_records(self) -> list[dict[str, Any]]:
        """Return all current ANS records as a JSON-serialisable list."""
        return [
            {
                "name":         r.name,
                "aim_uri":      r.aim_uri,
                "node_id":      r.node_id,
                "host":         r.host,
                "port":         r.port,
                "capabilities": list(r.capabilities),
                "creator":      r.creator,
                "ttl_seconds":  r.ttl_seconds,
            }
            for r in self._registry.all_records()
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_aim_scheme(name: str) -> str:
        """Remove the ``aim://`` prefix from a name, if present."""
        if name.lower().startswith("aim://"):
            return name[6:]
        return name

    def _to_ans_name(self, name: str) -> str | None:
        """
        Return a normalised bare ANS name if *name* looks like an ANS name,
        otherwise return ``None``.

        An ANS name is either prefixed with ``aim://`` or ends with ``.aim``.
        """
        bare = self._strip_aim_scheme(name).lower().strip()
        if name.lower().startswith("aim://") or bare.endswith(".aim"):
            return bare
        return None
