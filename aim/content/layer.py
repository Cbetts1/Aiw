"""
ContentLayer — signed, ledger-backed content store for the AIM mesh.

Every piece of content posted to the mesh is:

1. Assigned a unique ``content_id`` (UUID).
2. Signed by the poster's ``CreatorSignature``.
3. Recorded in the ``LegacyLedger`` (immutable audit trail).
4. Optionally cached by relay nodes for low-latency reads.

Usage
-----
::

    from aim.content.layer import ContentLayer
    from aim.identity.signature import CreatorSignature

    store = ContentLayer()
    sig   = CreatorSignature()
    item  = store.post("Hello, mesh!", "text", author_sig=sig)
    same  = store.get(item.content_id)
    store.delete(item.content_id, requester_sig=sig)
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

from aim.identity.signature import CreatorSignature, ORIGIN_CREATOR, AIM_MESH_NAME
from aim.identity.ledger import LegacyLedger, default_ledger

_EK_CONTENT_POSTED  = "content_posted"
_EK_CONTENT_DELETED = "content_deleted"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ContentItem:
    """
    An immutable content record in the AIM mesh.

    Fields
    ------
    content_id        : unique identifier (UUID)
    body              : the content payload (text, JSON string, base-64, …)
    content_type      : MIME-style hint (e.g. ``"text"``, ``"json"``)
    author            : display name of the posting creator
    signature_digest  : HMAC digest from the author's ``CreatorSignature``
    created_at        : Unix timestamp
    deleted           : soft-delete flag (set by :meth:`ContentLayer.delete`)
    """

    content_id:       str   = field(default_factory=lambda: str(uuid.uuid4()))
    body:             str   = ""
    content_type:     str   = "text"
    author:           str   = ORIGIN_CREATOR
    signature_digest: str   = ""
    created_at:       float = field(default_factory=time.time)
    deleted:          bool  = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ContentItem":
        return cls(**d)


# ---------------------------------------------------------------------------
# Content store
# ---------------------------------------------------------------------------

class ContentLayer:
    """
    Thread-safe, in-process content store backed by ``LegacyLedger``.

    Parameters
    ----------
    ledger : LegacyLedger instance to record events (default: global ledger)
    """

    def __init__(self, ledger: LegacyLedger | None = None) -> None:
        self._items: dict[str, ContentItem] = {}
        self._lock = threading.RLock()
        self._ledger = ledger or default_ledger()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def post(
        self,
        body: str,
        content_type: str = "text",
        *,
        author_sig: CreatorSignature | None = None,
    ) -> ContentItem:
        """
        Post a new content item.

        Parameters
        ----------
        body         : the content payload
        content_type : MIME-style type hint
        author_sig   : ``CreatorSignature`` of the poster; a default
                       (origin-creator) signature is used if omitted

        Returns
        -------
        ContentItem  : the newly created (and stored) item
        """
        if author_sig is None:
            author_sig = CreatorSignature()

        item = ContentItem(
            body=body,
            content_type=content_type,
            author=author_sig.creator,
            signature_digest=author_sig.digest,
        )
        with self._lock:
            self._items[item.content_id] = item

        self._ledger.record(
            _EK_CONTENT_POSTED,
            author_sig.node_id,
            payload={
                "content_id":   item.content_id,
                "content_type": item.content_type,
                "author":       item.author,
            },
            signature=author_sig,
        )
        return item

    def delete(
        self,
        content_id: str,
        *,
        requester_sig: CreatorSignature | None = None,
    ) -> bool:
        """
        Soft-delete a content item.

        Only the original author (matched by ``author`` field) may delete
        content.  If ``requester_sig`` is omitted the origin creator is
        assumed.

        Returns ``True`` if the item was found and marked deleted,
        ``False`` otherwise.
        """
        if requester_sig is None:
            requester_sig = CreatorSignature()

        with self._lock:
            item = self._items.get(content_id)
            if item is None or item.deleted:
                return False
            # Only the original author may delete
            if item.author != requester_sig.creator:
                return False
            item.deleted = True

        self._ledger.record(
            _EK_CONTENT_DELETED,
            requester_sig.node_id,
            payload={"content_id": content_id, "author": item.author},
            signature=requester_sig,
        )
        return True

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get(self, content_id: str) -> ContentItem | None:
        """Return a content item by ID, or ``None`` if not found / deleted."""
        with self._lock:
            item = self._items.get(content_id)
        if item is None or item.deleted:
            return None
        return item

    def list(
        self,
        limit: int = 50,
        after_ts: float = 0.0,
        content_type: str | None = None,
    ) -> list[ContentItem]:
        """
        Return up to *limit* non-deleted items created after *after_ts*.

        Items are returned in ascending ``created_at`` order.

        Parameters
        ----------
        limit        : maximum number of items to return
        after_ts     : only return items created after this Unix timestamp
        content_type : if given, filter to items with this ``content_type``
        """
        with self._lock:
            items = list(self._items.values())

        filtered = [
            it for it in items
            if not it.deleted and it.created_at > after_ts
            and (content_type is None or it.content_type == content_type)
        ]
        filtered.sort(key=lambda it: it.created_at)
        return filtered[:limit]

    def count(self) -> int:
        """Return total number of non-deleted items."""
        with self._lock:
            return sum(1 for it in self._items.values() if not it.deleted)
