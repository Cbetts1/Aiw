"""
AIM Content Node — an AgentNode extension that handles PUBLISH, READ,
and LIST intents via the content layer.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from aim.protocol.message import AIMMessage, Intent, Status
from aim.node.agent import AgentNode
from aim.content.store import ContentStore, default_store

_MAX_TITLE_CHARS = 200
_MAX_BODY_CHARS = 10_000


class ContentNode(AgentNode):
    """
    An AgentNode that also handles content-layer intents.

    Parameters
    ----------
    store       : ContentStore instance to use.  Defaults to the
                  module-level shared store.
    data_dir    : optional directory path; if given, a ContentStore backed
                  by ``<data_dir>/posts.jsonl`` is created automatically.
    All other parameters are forwarded to AgentNode / BaseNode.
    """

    def __init__(
        self,
        *args: Any,
        store: ContentStore | None = None,
        data_dir: str | Path | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if store is not None:
            self._content_store: ContentStore = store
        elif data_dir is not None:
            persist_path = os.path.join(str(data_dir), "posts.jsonl")
            self._content_store = ContentStore(persist_path=persist_path)
        else:
            self._content_store = default_store()
        self._register_content_handlers()

    # ------------------------------------------------------------------
    # Public dispatch API (used by test_posting.py / HTTP handlers)
    # ------------------------------------------------------------------

    async def dispatch(self, msg: AIMMessage) -> AIMMessage:
        """
        High-level dispatch for content intents (PUBLISH / READ / LIST).

        Unlike ``_handler.dispatch``, this method:
        - Applies posting-layer validation (title/body length, author default).
        - Returns ``"post"`` / ``"posts"`` keys for compatibility with the
          HTTP posting API.
        - Returns an error response for any non-content intent.
        """
        if msg.intent == Intent.PUBLISH:
            return await self._dispatch_publish(msg)
        if msg.intent == Intent.READ:
            return await self._dispatch_read(msg)
        if msg.intent == Intent.LIST:
            return await self._dispatch_list(msg)
        return AIMMessage.respond(
            correlation_id=msg.message_id,
            result={"error": f"unsupported intent: {msg.intent.value}"},
            status=Status.ERROR,
            sender_id=self.node_id,
            receiver_id=msg.sender_id,
        )

    async def _dispatch_publish(self, msg: AIMMessage) -> AIMMessage:
        p = msg.payload
        title = str(p.get("title", "")).strip()
        body = str(p.get("body", "")).strip()
        author = str(p.get("author", "")).strip() or "anonymous"

        if not title:
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"error": "title is required"},
                status=Status.ERROR,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )
        if len(title) > _MAX_TITLE_CHARS:
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"error": f"title exceeds {_MAX_TITLE_CHARS} characters"},
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
        if len(body) > _MAX_BODY_CHARS:
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"error": f"body exceeds {_MAX_BODY_CHARS} characters"},
                status=Status.ERROR,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )

        try:
            item = self._content_store.publish(
                body=body,
                author=author,
                title=title,
                tags=p.get("tags", []),
                visibility=p.get("visibility", "public"),
                content_type=p.get("content_type", "post"),
                author_sig=msg.signature or self.creator,
            )
            post = item.to_dict()
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"status": "published", "post": post},
                status=Status.OK,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )
        except ValueError as exc:
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"error": str(exc)},
                status=Status.ERROR,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )

    async def _dispatch_read(self, msg: AIMMessage) -> AIMMessage:
        content_id = str(msg.payload.get("id", "")).strip()
        if not content_id:
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"error": "id is required"},
                status=Status.ERROR,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )
        item = self._content_store.read(content_id)
        if item is None:
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"error": f"Post {content_id!r} not found"},
                status=Status.ERROR,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )
        return AIMMessage.respond(
            correlation_id=msg.message_id,
            result={"post": item.to_dict()},
            status=Status.OK,
            sender_id=self.node_id,
            receiver_id=msg.sender_id,
        )

    async def _dispatch_list(self, msg: AIMMessage) -> AIMMessage:
        p = msg.payload
        filters: dict[str, Any] = {
            "author": p.get("author"),
            "tag": p.get("tag"),
            "visibility": p.get("visibility"),
            "content_type": p.get("content_type"),
        }
        try:
            limit = int(p.get("limit", 50))
        except (TypeError, ValueError):
            limit = 50
        # Total matching count (before limit) — efficient, no full fetch
        total_count = self._content_store.count_matching(**filters)
        posts = self._content_store.list(**filters, limit=limit, offset=0)
        return AIMMessage.respond(
            correlation_id=msg.message_id,
            result={
                "count": total_count,
                "posts": [i.to_dict() for i in posts],
            },
            status=Status.OK,
            sender_id=self.node_id,
            receiver_id=msg.sender_id,
        )

    # ------------------------------------------------------------------
    # Persistence helper
    # ------------------------------------------------------------------

    def _load(self) -> list[dict[str, Any]]:
        """Return all stored posts as a list of dicts (newest first)."""
        total = self._content_store.count()
        return [i.to_dict() for i in self._content_store.list(limit=max(total, 1))]

    # ------------------------------------------------------------------
    # Content intent handlers (used via _handler.dispatch)
    # ------------------------------------------------------------------

    def _register_content_handlers(self) -> None:

        @self._handler.on(Intent.PUBLISH)
        async def _on_publish(msg: AIMMessage) -> AIMMessage:
            p = msg.payload
            try:
                item = self._content_store.publish(
                    body=p.get("body", ""),
                    author=p.get("author", msg.sender_id or self.creator),
                    title=p.get("title", ""),
                    tags=p.get("tags", []),
                    visibility=p.get("visibility", "public"),
                    content_type=p.get("content_type", "post"),
                    author_sig=msg.signature or self.creator,
                )
                return AIMMessage.respond(
                    correlation_id=msg.message_id,
                    result={"status": "published", "item": item.to_dict()},
                    status=Status.OK,
                    sender_id=self.node_id,
                    receiver_id=msg.sender_id,
                )
            except ValueError as exc:
                return AIMMessage.respond(
                    correlation_id=msg.message_id,
                    result={"error": str(exc)},
                    status=Status.ERROR,
                    sender_id=self.node_id,
                    receiver_id=msg.sender_id,
                )

        @self._handler.on(Intent.READ)
        async def _on_read(msg: AIMMessage) -> AIMMessage:
            content_id = str(msg.payload.get("id", "")).strip()
            if not content_id:
                return AIMMessage.respond(
                    correlation_id=msg.message_id,
                    result={"error": "id is required"},
                    status=Status.ERROR,
                    sender_id=self.node_id,
                    receiver_id=msg.sender_id,
                )
            item = self._content_store.read(content_id)
            if item is None:
                return AIMMessage.respond(
                    correlation_id=msg.message_id,
                    result={"error": f"Content item {content_id!r} not found"},
                    status=Status.ERROR,
                    sender_id=self.node_id,
                    receiver_id=msg.sender_id,
                )
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={"item": item.to_dict()},
                status=Status.OK,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )

        @self._handler.on(Intent.LIST)
        async def _on_list(msg: AIMMessage) -> AIMMessage:
            p = msg.payload
            items = self._content_store.list(
                author=p.get("author"),
                tag=p.get("tag"),
                visibility=p.get("visibility"),
                content_type=p.get("content_type"),
                limit=int(p.get("limit", 50)),
                offset=int(p.get("offset", 0)),
            )
            return AIMMessage.respond(
                correlation_id=msg.message_id,
                result={
                    "count": len(items),
                    "items": [i.to_dict() for i in items],
                },
                status=Status.OK,
                sender_id=self.node_id,
                receiver_id=msg.sender_id,
            )

