"""
AIM Content Layer — ContentNode

Handles PUBLISH, READ, and LIST intents and persists content items to a
JSON file under the AIM data directory.  The node is consumed in-process
by the web bridge; no TCP socket is required.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from aim.protocol.message import AIMMessage, Intent, Status

# ---------------------------------------------------------------------------
# Data directory (mirrors aim/web/server.py convention)
# ---------------------------------------------------------------------------


def _default_data_dir() -> Path:
    env = os.environ.get("AIM_DATA_DIR", "").strip()
    if env:
        return Path(env)
    return Path.home() / ".local" / "share" / "aim"


_MAX_ITEMS = 1000  # cap to prevent unbounded growth


class ContentNode:
    """
    An in-process AIM node that stores and retrieves content items.

    Content items have the shape::

        {
            "id":        str,          # UUID
            "title":     str,
            "body":      str,
            "author":    str,
            "timestamp": int,          # Unix epoch seconds
        }

    Parameters
    ----------
    data_dir : Path or str, optional
        Directory where ``content_posts.json`` is stored.
        Defaults to ``_default_data_dir()``.
    """

    node_id: str = "content-node"

    def __init__(self, data_dir: Path | str | None = None) -> None:
        base = Path(data_dir) if data_dir is not None else _default_data_dir()
        base.mkdir(parents=True, exist_ok=True)
        self._posts_file = base / "content_posts.json"
        if not self._posts_file.exists():
            self._posts_file.write_text("[]", encoding="utf-8")

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self._posts_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (OSError, json.JSONDecodeError):
            pass
        return []

    def _save(self, posts: list[dict[str, Any]]) -> None:
        self._posts_file.write_text(
            json.dumps(posts, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    async def _handle_publish(self, msg: AIMMessage) -> AIMMessage:
        title  = str(msg.payload.get("title", "")).strip()
        body   = str(msg.payload.get("body",  "")).strip()
        author = str(msg.payload.get("author", "anonymous")).strip() or "anonymous"

        if not title:
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"error": "title is required"},
                status=Status.ERROR,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )
        if not body:
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"error": "body is required"},
                status=Status.ERROR,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )
        if len(title) > 200:
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"error": "title must be 200 characters or fewer"},
                status=Status.ERROR,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )
        if len(body) > 10_000:
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"error": "body must be 10 000 characters or fewer"},
                status=Status.ERROR,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )
        if len(author) > 60:
            author = author[:60]

        post: dict[str, Any] = {
            "id":        str(uuid.uuid4()),
            "title":     title,
            "body":      body,
            "author":    author,
            "timestamp": int(time.time()),
        }

        posts = self._load()
        posts.append(post)
        if len(posts) > _MAX_ITEMS:
            posts = posts[-_MAX_ITEMS:]
        self._save(posts)

        return AIMMessage.respond(
            correlation_id=msg.message_id,
            result={"status": "published", "post": post},
            sender_id=self.node_id,
            receiver_id=msg.sender_id,
        )

    async def _handle_read(self, msg: AIMMessage) -> AIMMessage:
        content_id = str(msg.payload.get("id", "")).strip()
        if not content_id:
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"error": "id is required"},
                status=Status.ERROR,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )

        posts = self._load()
        for post in posts:
            if post.get("id") == content_id:
                return AIMMessage.respond(
                    correlation_id=msg.message_id,
                    result={"post": post},
                    sender_id=self.node_id,
                    receiver_id=msg.sender_id,
                )

        return AIMMessage.respond(
            correlation_id=msg.message_id,
            result={"error": f"post {content_id!r} not found"},
            status=Status.ERROR,
            sender_id=self.node_id,
            receiver_id=msg.sender_id,
        )

    async def _handle_list(self, msg: AIMMessage) -> AIMMessage:
        try:
            limit = int(msg.payload.get("limit", 50))
            limit = max(1, min(limit, _MAX_ITEMS))
        except (TypeError, ValueError):
            limit = 50

        posts = self._load()
        newest_first = list(reversed(posts))
        page = newest_first[:limit]

        return AIMMessage.respond(
            correlation_id=msg.message_id,
            result={"count": len(posts), "posts": page},
            sender_id=self.node_id,
            receiver_id=msg.sender_id,
        )

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def dispatch(self, msg: AIMMessage) -> AIMMessage:
        """Route an AIMMessage to the appropriate handler."""
        if msg.intent == Intent.PUBLISH:
            return await self._handle_publish(msg)
        if msg.intent == Intent.READ:
            return await self._handle_read(msg)
        if msg.intent == Intent.LIST:
            return await self._handle_list(msg)

        return AIMMessage.respond(
            correlation_id=msg.message_id,
            result={"error": f"unsupported intent: {msg.intent.value}"},
            status=Status.ERROR,
            sender_id=self.node_id,
            receiver_id=msg.sender_id,
        )
