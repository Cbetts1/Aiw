"""
Meshara Name Service (ANS) — human-readable names for Meshara nodes.

ANS maps `meshara://` URIs to NodeRecord addresses, analogous to DNS for the web.

    from meshara.ans import ANSRegistry, ANSRecord, ANSResolver

    registry = ANSRegistry()
    registry.register(ANSRecord(
        name="weather.public.meshara",
        node_id="some-uuid",
        host="127.0.0.1",
        port=7700,
        capabilities=["query"],
    ))

    resolver = ANSResolver(registry)
    record = resolver.resolve("meshara://weather.public.meshara")
"""

from meshara.ans.registry import ANSRegistry, ANSRecord
from meshara.ans.resolver import ANSResolver

__all__ = ["ANSRegistry", "ANSRecord", "ANSResolver"]
