"""
AIM Name Service (ANS) — human-readable names for AIM nodes.

ANS maps `aim://` URIs to NodeRecord addresses, analogous to DNS for the web.

    from aim.ans import ANSRegistry, ANSRecord, ANSResolver

    registry = ANSRegistry()
    registry.register(ANSRecord(
        name="weather.public.aim",
        node_id="some-uuid",
        host="127.0.0.1",
        port=7700,
        capabilities=["query"],
    ))

    resolver = ANSResolver(registry)
    record = resolver.resolve("aim://weather.public.aim")
"""

from aim.ans.registry import ANSRegistry, ANSRecord
from aim.ans.resolver import ANSResolver

__all__ = ["ANSRegistry", "ANSRecord", "ANSResolver"]
