"""
AIM Content Store — append-only JSONL-backed storage for content items.

Every item is traceable to a CreatorSignature, consistent with the
LegacyLedger append-only design.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

from aim.identity.signature import ORIGIN_CREATOR


# ---------------------------------------------------------------------------
# Content item schema
# ---------------------------------------------------------------------------

MAX_BODY_BYTES   = 65_536   # 64 KiB
MAX_TITLE_CHARS  = 200
MAX_TAGS         = 20
MAX_TAG_CHARS    = 50
ALLOWED_VISIBILITY = {"public", "private"}


@dataclass
class ContentItem:
    """
    A single piece of content in the AIM mesh.

    Fields
    ------
    id          : unique identifier (UUID4, auto-generated)
    author      : free-form author handle or node identifier
    timestamp   : Unix epoch seconds (auto-set on creation)
    signature   : origin-creator digest — every item must be traceable
    body        : main text / markdown content (max 64 KiB)
    title       : optional short title (max 200 chars)
    tags        : list of searchable labels (max 20, each ≤ 50 chars)
    visibility  : "public" or "private" (default "public")
    content_type: hint for consumers, e.g. "post", "page", "note"
    """

    body:         str
    author:       str         = ORIGIN_CREATOR
    title:        str         = ""
    tags:         list[str]   = field(default_factory=list)
    visibility:   str         = "public"
    content_type: str         = "post"
    signature:    str         = ORIGIN_CREATOR
    id:           str         = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:    float       = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ContentItem":
        # Accept only known fields to avoid unexpected kwargs
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# Content store
# ---------------------------------------------------------------------------

class ContentStore:
    """
    Thread-safe append-only content store backed by a JSONL file.

    Parameters
    ----------
    persist_path : optional path for JSONL persistence.
                   If given, every published item is appended to the file.
    """

    def __init__(self, persist_path: str | None = None) -> None:
        self._items: dict[str, ContentItem] = {}   # id → item
        self._order: list[str] = []                # insertion order
        self._lock = threading.RLock()
        self._persist_path = persist_path
        if persist_path and os.path.exists(persist_path):
            self._load(persist_path)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def publish(
        self,
        body: str,
        author: str = ORIGIN_CREATOR,
        title: str = "",
        tags: list[str] | None = None,
        visibility: str = "public",
        content_type: str = "post",
        author_sig: str = ORIGIN_CREATOR,
    ) -> ContentItem:
        """
        Create and store a new content item.

        Parameters
        ----------
        body        : main content text (required)
        author      : author handle or node identifier
        title       : optional title
        tags        : list of tag strings
        visibility  : "public" or "private"
        content_type: "post", "page", "note", …
        author_sig  : origin-creator signature digest for traceability

        Returns
        -------
        The newly created ContentItem.

        Raises
        ------
        ValueError on validation failures.
        """
        body = str(body)
        if not body.strip():
            raise ValueError("body must not be empty")
        if len(body.encode("utf-8")) > MAX_BODY_BYTES:
            raise ValueError(f"body exceeds {MAX_BODY_BYTES} bytes")

        title = str(title)[:MAX_TITLE_CHARS]

        raw_tags: list[str] = tags or []
        if not isinstance(raw_tags, list):
            raise ValueError("tags must be a list")
        clean_tags = [str(t)[:MAX_TAG_CHARS] for t in raw_tags[:MAX_TAGS]]

        visibility = str(visibility).lower()
        if visibility not in ALLOWED_VISIBILITY:
            visibility = "public"

        item = ContentItem(
            body=body,
            author=str(author)[:120],
            title=title,
            tags=clean_tags,
            visibility=visibility,
            content_type=str(content_type)[:60],
            signature=str(author_sig),
        )

        with self._lock:
            self._items[item.id] = item
            self._order.append(item.id)

        if self._persist_path:
            self._append_to_file(item)

        return item

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read(self, content_id: str) -> ContentItem | None:
        """Return the item with the given id, or None if not found."""
        with self._lock:
            return self._items.get(content_id)

    def list(
        self,
        author: str | None = None,
        tag: str | None = None,
        visibility: str | None = None,
        content_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ContentItem]:
        """
        Return content items matching the given filters (newest first).

        Parameters
        ----------
        author       : filter by exact author string
        tag          : filter to items that include this tag
        visibility   : filter by "public" or "private"
        content_type : filter by content_type
        limit        : max number of results (default 50, max 200)
        offset       : skip the first *offset* matching items
        """
        limit  = max(1, min(int(limit), 200))
        offset = max(0, int(offset))

        with self._lock:
            # Newest first: reverse insertion order
            ordered = [self._items[i] for i in reversed(self._order)]

        results: list[ContentItem] = []
        for item in ordered:
            if author is not None and item.author != author:
                continue
            if tag is not None and tag not in item.tags:
                continue
            if visibility is not None and item.visibility != visibility:
                continue
            if content_type is not None and item.content_type != content_type:
                continue
            results.append(item)

        return results[offset : offset + limit]

    def count_matching(
        self,
        author: str | None = None,
        tag: str | None = None,
        visibility: str | None = None,
        content_type: str | None = None,
    ) -> int:
        """Return the number of items matching the given filters."""
        with self._lock:
            ordered = list(self._items.values())
        total = 0
        for item in ordered:
            if author is not None and item.author != author:
                continue
            if tag is not None and tag not in item.tags:
                continue
            if visibility is not None and item.visibility != visibility:
                continue
            if content_type is not None and item.content_type != content_type:
                continue
            total += 1
        return total

    def count(self) -> int:
        with self._lock:
            return len(self._items)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _append_to_file(self, item: ContentItem) -> None:
        try:
            with open(self._persist_path, "a", encoding="utf-8") as fh:  # type: ignore[arg-type]
                fh.write(json.dumps(item.to_dict()) + "\n")
        except OSError:
            pass  # best-effort persistence

    def _load(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        item = ContentItem.from_dict(d)
                        self._items[item.id] = item
                        self._order.append(item.id)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Module-level default store (shared across the process unless overridden)
# ---------------------------------------------------------------------------

_default_store: ContentStore | None = None
_ds_lock = threading.Lock()


def default_store(persist_path: str | None = None) -> ContentStore:
    global _default_store
    with _ds_lock:
        if _default_store is None:
            _default_store = ContentStore(persist_path=persist_path)
        return _default_store
