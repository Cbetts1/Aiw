"""
AIM Content Layer — signed, ledger-backed content store.

Content items are immutable once posted (origin signature is embedded).
Deletion is a soft-delete: the item is marked removed but the ledger entry
is permanent.
"""

from aim.content.layer import ContentLayer, ContentItem

__all__ = ["ContentLayer", "ContentItem"]
