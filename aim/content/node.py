"""
AIM Content Node — an AgentNode extension that handles PUBLISH, READ,
and LIST intents via the content layer.
"""

from __future__ import annotations

from typing import Any

from aim.protocol.message import AIMMessage, Intent, Status
from aim.node.agent import AgentNode
from aim.content.store import ContentStore, default_store


class ContentNode(AgentNode):
    """
    An AgentNode that also handles content-layer intents.

    Parameters
    ----------
    store       : ContentStore instance to use.  Defaults to the
                  module-level shared store.
    All other parameters are forwarded to AgentNode / BaseNode.
    """

    def __init__(
        self,
        *args: Any,
        store: ContentStore | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._content_store: ContentStore = store or default_store()
        self._register_content_handlers()

    # ------------------------------------------------------------------
    # Content intent handlers
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
