"""
AIM Command Center — CommandCenterNode.

A specialised :class:`~aim.node.agent.AgentNode` that maintains a live
connection to a Command Center server for remote management, health
reporting, and command dispatch.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from aim.node.agent import AgentNode
from aim.command_center.identity import VirtualDeviceIdentity
from aim.command_center.client import CommandCenterClient
from aim.identity.signature import ORIGIN_CREATOR

logger = logging.getLogger(__name__)


class CommandCenterNode(AgentNode):
    """
    An AgentNode pre-wired to a remote Command Center.

    Extra Parameters
    ----------------
    cc_host : Hostname or IP of the Command Center server.
    cc_port : TCP port of the Command Center server.
    node_name : Human-readable name for this device (default ``"aim-cc-node"``).
    repo_url  : Source repository URL embedded in the device identity.
    heartbeat_interval : Seconds between HEARTBEAT frames to the CC.
    health_report_interval : Seconds between automatic health reports.
    All remaining parameters are forwarded to :class:`~aim.node.agent.AgentNode`.
    """

    CREATOR: str = ORIGIN_CREATOR

    def __init__(
        self,
        *args: Any,
        cc_host: str = "127.0.0.1",
        cc_port: int = 9000,
        node_name: str = "aim-cc-node",
        repo_url: str = "https://github.com/Cbetts1/Aiw",
        heartbeat_interval: float = 30.0,
        health_report_interval: float = 60.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._cc_host = cc_host
        self._cc_port = cc_port
        self._node_name = node_name
        self._repo_url = repo_url
        self._heartbeat_interval = heartbeat_interval
        self._health_report_interval = health_report_interval

        self._device_identity: VirtualDeviceIdentity | None = None
        self._cc_client: CommandCenterClient | None = None
        self._health_task: asyncio.Task[None] | None = None  # type: ignore[type-arg]
        self._started_at: float = time.time()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the AgentNode server and connect to the Command Center."""
        # Initialise identity and client
        self._device_identity = VirtualDeviceIdentity.new(
            name=self._node_name,
            repo_url=self._repo_url,
            capabilities=list(self.capabilities),
        )
        self._cc_client = CommandCenterClient(
            cc_host=self._cc_host,
            cc_port=self._cc_port,
            device_identity=self._device_identity,
            heartbeat_interval=self._heartbeat_interval,
        )
        self._register_builtin_cc_handlers()

        # Connect to CC (best-effort — node runs even if CC is unreachable)
        try:
            await self._cc_client.connect()
            logger.info(
                "CommandCenterNode %s connected to CC at %s:%s",
                self.node_id[:8],
                self._cc_host,
                self._cc_port,
            )
        except Exception as exc:
            logger.warning("Could not connect to CC (%s) — running standalone", exc)

        # Launch periodic health reporter
        self._health_task = asyncio.create_task(
            self._health_report_loop(), name="cc-health"
        )

        # Delegate to parent (blocks until stopped)
        await super().start()

    async def stop(self) -> None:
        """Stop health reporting, disconnect from CC, then stop the node."""
        if self._health_task and not self._health_task.done():
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

        if self._cc_client and self._cc_client.is_connected:
            await self._cc_client.disconnect()

        await super().stop()

    # ------------------------------------------------------------------
    # Health reporting
    # ------------------------------------------------------------------

    async def report_health(self) -> None:
        """Collect a health snapshot and send it to the Command Center."""
        if not self._cc_client or not self._cc_client.is_connected:
            return

        metrics = {
            "uptime": time.time() - self._started_at,
            "peer_count": len(self._peers),
            "task_count": len(getattr(self, "_task_results", {})),
            "node_id": self.node_id,
        }
        await self._cc_client.send_status(metrics)

    async def _health_report_loop(self) -> None:
        """Background task: report health to the CC every interval."""
        while True:
            try:
                await asyncio.sleep(self._health_report_interval)
                await self.report_health()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Health report error: %s", exc)

    # ------------------------------------------------------------------
    # Built-in CC command handlers
    # ------------------------------------------------------------------

    def _register_builtin_cc_handlers(self) -> None:
        """Register default command handlers for common CC intents."""
        client = self._cc_client
        assert client is not None

        @client.on_command("query")
        async def _handle_query(cmd: dict[str, Any]) -> None:
            text = cmd.get("text", "")
            result = await self.engine.reason(text, {})
            logger.info("CC query=%r → %r", text, result)

        @client.on_command("status")
        async def _handle_status(cmd: dict[str, Any]) -> None:
            await self.report_health()

        @client.on_command("shutdown")
        async def _handle_shutdown(cmd: dict[str, Any]) -> None:
            logger.warning("CC requested shutdown of node %s", self.node_id[:8])
            await self.stop()

        @client.on_command("reload")
        async def _handle_reload(cmd: dict[str, Any]) -> None:
            logger.info("CC requested reload — re-registering handlers")
            self._register_memory_handlers()
