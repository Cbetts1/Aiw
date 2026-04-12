"""
AIM Command Center — TCP client.

``CommandCenterClient`` connects an AIM virtual device to a remote Command
Center server.  It speaks the same 4-byte length-prefix framing used
everywhere else in the mesh.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

# Wire-level framing: 4-byte big-endian length prefix + UTF-8 JSON payload
_LENGTH_PREFIX_BYTES = 4


# ---------------------------------------------------------------------------
# Low-level framing helpers
# ---------------------------------------------------------------------------

async def _send_frame(writer: asyncio.StreamWriter, data: dict[str, Any]) -> None:
    raw = json.dumps(data).encode()
    writer.write(len(raw).to_bytes(_LENGTH_PREFIX_BYTES, "big") + raw)
    await writer.drain()


async def _recv_frame(
    reader: asyncio.StreamReader,
) -> dict[str, Any] | None:
    try:
        raw_len = await reader.readexactly(_LENGTH_PREFIX_BYTES)
        length = int.from_bytes(raw_len, "big")
        raw = await reader.readexactly(length)
        return json.loads(raw.decode())
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ValueError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class CommandCenterClient:
    """
    Async TCP client that keeps a virtual device registered with the CC.

    Parameters
    ----------
    cc_host            : Hostname or IP of the Command Center server.
    cc_port            : TCP port of the Command Center server.
    device_identity    : :class:`~aim.command_center.identity.VirtualDeviceIdentity`
                         used for the REGISTER handshake.
    heartbeat_interval : Seconds between HEARTBEAT frames (default 30).
    """

    def __init__(
        self,
        cc_host: str,
        cc_port: int,
        device_identity: Any,  # VirtualDeviceIdentity — avoid circular import
        heartbeat_interval: float = 30.0,
    ) -> None:
        self._host = cc_host
        self._port = cc_port
        self._identity = device_identity
        self._heartbeat_interval = heartbeat_interval

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False

        self._heartbeat_task: asyncio.Task[None] | None = None  # type: ignore[type-arg]
        self._listener_task: asyncio.Task[None] | None = None   # type: ignore[type-arg]

        # intent → async handler
        self._handlers: dict[str, Callable[[dict[str, Any]], Awaitable[None]]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """True while the TCP connection to the CC is live."""
        return self._connected

    async def connect(self) -> None:
        """Open connection, register identity, start background tasks."""
        await self._do_connect()

    async def disconnect(self) -> None:
        """Gracefully stop background tasks and close the connection."""
        self._connected = False
        for task in (self._heartbeat_task, self._listener_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None
        logger.info("CC client disconnected from %s:%s", self._host, self._port)

    async def send_status(self, metrics: dict[str, Any]) -> None:
        """Send a STATUS frame carrying the supplied *metrics* dict."""
        if not self._connected or not self._writer:
            logger.warning("send_status called while not connected — dropping")
            return
        await _send_frame(self._writer, {
            "type": "STATUS",
            "device_id": self._identity.device_id,
            "metrics": metrics,
            "ts": time.time(),
        })

    # ------------------------------------------------------------------
    # Command handler registration
    # ------------------------------------------------------------------

    def on_command(self, intent: str) -> Callable:
        """
        Decorator: register an async handler for the given command *intent*.

        Example
        -------
        ::

            @client.on_command("reload")
            async def handle_reload(cmd: dict) -> None:
                ...
        """
        def decorator(func: Callable[[dict[str, Any]], Awaitable[None]]) -> Callable:
            self._handlers[intent] = func
            return func
        return decorator

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _do_connect(self) -> None:
        """Establish TCP connection and start background loops."""
        self._reader, self._writer = await asyncio.open_connection(
            self._host, self._port
        )
        self._connected = True
        logger.info(
            "CC client connected to %s:%s as %s",
            self._host, self._port, self._identity,
        )

        # Send REGISTER
        await _send_frame(self._writer, {
            "type": "REGISTER",
            "identity": self._identity.to_dict(),
            "ts": time.time(),
        })

        # Start background loops
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name="cc-heartbeat"
        )
        self._listener_task = asyncio.create_task(
            self._command_listener(), name="cc-listener"
        )

    async def _heartbeat_loop(self) -> None:
        """Send periodic HEARTBEAT frames to the CC."""
        while self._connected:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                if self._connected and self._writer:
                    await _send_frame(self._writer, {
                        "type": "HEARTBEAT",
                        "device_id": self._identity.device_id,
                        "ts": time.time(),
                    })
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("CC heartbeat error: %s — reconnecting", exc)
                await self._reconnect_with_backoff()

    async def _command_listener(self) -> None:
        """Read frames from the CC and dispatch registered handlers."""
        while self._connected and self._reader:
            frame = await _recv_frame(self._reader)
            if frame is None:
                if self._connected:
                    logger.warning("CC connection lost — reconnecting")
                    await self._reconnect_with_backoff()
                break
            await self._handle_remote_command(frame)

    async def _handle_remote_command(self, cmd: dict[str, Any]) -> None:
        """Dispatch a received command frame to the matching handler."""
        intent = cmd.get("intent") or cmd.get("type", "")
        handler = self._handlers.get(intent)
        if handler:
            try:
                await handler(cmd)
            except Exception as exc:
                logger.error("Handler for %r raised: %s", intent, exc)
        else:
            logger.debug("No handler for CC command intent=%r", intent)

    async def _reconnect_with_backoff(self) -> None:
        """Re-establish the connection with exponential back-off (max 60s)."""
        self._connected = False
        if self._writer:
            try:
                self._writer.close()
            except Exception:
                pass
            self._reader = None
            self._writer = None

        delay = 1.0
        while not self._connected:
            try:
                logger.info("Reconnecting to CC in %.0fs…", delay)
                await asyncio.sleep(delay)
                await self._do_connect()
            except Exception as exc:
                logger.warning("Reconnect failed: %s", exc)
                delay = min(delay * 2, 60.0)
