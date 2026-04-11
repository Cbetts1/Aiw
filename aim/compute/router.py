"""
AIM Task Router — routes tasks to capable nodes across the mesh.

Routing strategies
------------------
FIRST       : send to the first capable node found
ROUND_ROBIN : cycle through capable nodes in order
BROADCAST   : send to all capable nodes (fire-and-forget)
RELAY       : route through a healthy relay node as an intermediate hop
              (used for cross-subnet / cross-region traffic)
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
from enum import Enum
from typing import Any

from aim.node.registry import NodeRegistry, NodeRecord
from aim.protocol.message import AIMMessage, Intent

logger = logging.getLogger(__name__)


class RoutingStrategy(str, Enum):
    FIRST       = "first"
    ROUND_ROBIN = "round_robin"
    BROADCAST   = "broadcast"
    RELAY       = "relay"


class TaskRouter:
    """
    Routes AIM task messages to nodes registered in a NodeRegistry.

    Parameters
    ----------
    registry        : the NodeRegistry to query for capable nodes
    strategy        : default routing strategy
    relay_registry  : optional RelayRegistry; required when strategy=RELAY
    """

    def __init__(
        self,
        registry: NodeRegistry | None = None,
        strategy: RoutingStrategy = RoutingStrategy.FIRST,
        relay_registry: Any | None = None,
    ) -> None:
        self._registry = registry or NodeRegistry.default()
        self._strategy = strategy
        self._rr_counters: dict[str, int] = {}  # capability → next index
        self._relay_registry = relay_registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def route(
        self,
        task_name: str,
        args: dict[str, Any] | None = None,
        capability: str | None = None,
        strategy: RoutingStrategy | None = None,
        sender_id: str = "",
        timeout: float = 5.0,
    ) -> list[AIMMessage]:
        """
        Route a task to one or more nodes.

        Parameters
        ----------
        task_name  : name of the task to execute
        args       : task arguments
        capability : filter nodes by capability tag (defaults to task_name)
        strategy   : override the router's default strategy for this call
        sender_id  : originating node id (stamped on the outgoing message)
        timeout    : per-node connection timeout in seconds

        Returns
        -------
        List of response AIMMessages (one per contacted node).
        """
        cap = capability or task_name
        candidates = self._registry.find_by_capability(cap)
        if not candidates:
            logger.warning("No nodes with capability %r found", cap)
            return []

        strat = strategy or self._strategy
        targets = self._select_targets(candidates, cap, strat)

        msg = AIMMessage.task(task_name, args or {}, sender_id=sender_id)

        if strat == RoutingStrategy.RELAY:
            responses = await asyncio.gather(
                *[self._dispatch_via_relay(msg, node, timeout) for node in targets],
                return_exceptions=True,
            )
        else:
            responses = await asyncio.gather(
                *[self._dispatch(msg, node, timeout) for node in targets],
                return_exceptions=True,
            )
        results: list[AIMMessage] = []
        for r in responses:
            if isinstance(r, AIMMessage):
                results.append(r)
            elif isinstance(r, Exception):
                logger.warning("Routing error: %s", r)
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _select_targets(
        self,
        candidates: list[NodeRecord],
        capability: str,
        strategy: RoutingStrategy,
    ) -> list[NodeRecord]:
        if strategy == RoutingStrategy.BROADCAST:
            return candidates
        if strategy in (RoutingStrategy.FIRST, RoutingStrategy.RELAY):
            return [candidates[0]]
        # ROUND_ROBIN
        idx = self._rr_counters.get(capability, 0) % len(candidates)
        self._rr_counters[capability] = idx + 1
        return [candidates[idx]]

    @staticmethod
    async def _dispatch(
        msg: AIMMessage, node: NodeRecord, timeout: float
    ) -> AIMMessage | None:
        """Open a raw TCP connection to *node* and send *msg*."""
        from aim.node.base import _send_message, _recv_message

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(node.host, node.port), timeout=timeout
            )
        except (OSError, asyncio.TimeoutError) as exc:
            logger.warning("Cannot reach node %s: %s", node.node_id[:8], exc)
            return None

        try:
            await _send_message(writer, msg)
            response = await asyncio.wait_for(_recv_message(reader), timeout=timeout)
            return response
        except asyncio.TimeoutError:
            logger.warning("Timeout from node %s", node.node_id[:8])
            return None
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _dispatch_via_relay(
        self, msg: AIMMessage, node: NodeRecord, timeout: float
    ) -> AIMMessage | None:
        """
        Route *msg* to *node* through a healthy relay from the relay registry.

        Falls back to direct dispatch if no relay is available.
        """
        from aim.node.base import _send_message, _recv_message

        relay_reg = self._relay_registry
        relay = None
        if relay_reg is not None:
            relay = relay_reg.pick_round_robin()

        if relay is None:
            logger.debug("No healthy relay found, falling back to direct dispatch")
            return await self._dispatch(msg, node, timeout)

        # Build a FORWARD envelope targeting *node*
        forward_msg = AIMMessage(
            intent=Intent.FORWARD,
            payload={
                "target_host": node.host,
                "target_port": node.port,
                "message": json.loads(msg.to_json()),
            },
            sender_id=msg.sender_id,
            ttl=msg.ttl,
        )

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(relay.host, relay.port), timeout=timeout
            )
        except (OSError, asyncio.TimeoutError) as exc:
            logger.warning(
                "Cannot reach relay %s: %s — falling back to direct", relay.relay_id[:8], exc
            )
            return await self._dispatch(msg, node, timeout)

        try:
            await _send_message(writer, forward_msg)
            relay_response = await asyncio.wait_for(_recv_message(reader), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Timeout from relay %s", relay.relay_id[:8])
            return await self._dispatch(msg, node, timeout)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

        if relay_response is None:
            return await self._dispatch(msg, node, timeout)

        # Unwrap the response that the relay proxied from the target node
        inner = relay_response.payload.get("result", {}).get("response")
        if isinstance(inner, dict):
            try:
                return AIMMessage.from_json(json.dumps(inner))
            except Exception:
                pass
        return relay_response
