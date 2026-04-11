"""
Meshara Protocol handler — dispatches incoming messages to registered handlers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from .message import MesharaMessage, Intent

logger = logging.getLogger(__name__)

HandlerFn = Callable[[MesharaMessage], Awaitable[MesharaMessage | None]]


class ProtocolHandler:
    """
    Routes incoming Meshara messages to the appropriate handler functions.

    Usage
    -----
    handler = ProtocolHandler()

    @handler.on(Intent.QUERY)
    async def handle_query(msg):
        return MesharaMessage.respond(msg.message_id, result="42")

    response = await handler.dispatch(incoming_message)
    """

    def __init__(self) -> None:
        self._handlers: dict[Intent, list[HandlerFn]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def on(self, intent: Intent) -> Callable[[HandlerFn], HandlerFn]:
        """Decorator that registers a handler for the given intent."""
        def decorator(fn: HandlerFn) -> HandlerFn:
            self._handlers.setdefault(intent, []).append(fn)
            return fn
        return decorator

    def register(self, intent: Intent, fn: HandlerFn) -> None:
        """Programmatically register a handler."""
        self._handlers.setdefault(intent, []).append(fn)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def dispatch(self, message: MesharaMessage) -> MesharaMessage | None:
        """
        Dispatch *message* to all registered handlers for its intent.

        Returns the response produced by the first handler that returns a
        non-None value, or None if no handler responds.
        """
        handlers = self._handlers.get(message.intent, [])
        if not handlers:
            logger.debug("No handler registered for intent %s", message.intent)
            return None

        for fn in handlers:
            try:
                result = await fn(message)
                if result is not None:
                    return result
            except Exception:
                logger.exception("Handler %s raised an exception", fn.__name__)
        return None

    # ------------------------------------------------------------------
    # Batch processing
    # ------------------------------------------------------------------

    async def process_queue(
        self,
        queue: asyncio.Queue[MesharaMessage],
        output_queue: asyncio.Queue[MesharaMessage] | None = None,
    ) -> None:
        """Continuously drain *queue*, dispatching each message."""
        while True:
            message = await queue.get()
            try:
                response = await self.dispatch(message)
                if response is not None and output_queue is not None:
                    await output_queue.put(response)
            finally:
                queue.task_done()
