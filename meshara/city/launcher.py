"""
CityLauncher — automated one-call launch of the full Meshara city bot fleet.

Usage
-----
    from meshara.city.launcher import CityLauncher, CityConfig

    launcher = CityLauncher(CityConfig(host="0.0.0.0"))
    await launcher.launch()       # starts all five bots concurrently
    await launcher.shutdown()     # graceful stop
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from meshara.node.registry import NodeRegistry, NodeRecord
from meshara.identity.ledger import LegacyLedger
from meshara.city.governor import CityGovernorBot
from meshara.city.protector import ProtectionAgent
from meshara.city.builder import BuilderBot
from meshara.city.educator import EducationBot
from meshara.city.architect import ArchitectBot
from meshara.city.integrity import IntegrityGuard

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class CityConfig:
    """Port-layout and optional settings for an Meshara city deployment."""
    host:            str             = "127.0.0.1"
    governor_port:   int             = 7800
    protector_port:  int             = 7801
    builder_port:    int             = 7802
    educator_port:   int             = 7803
    architect_port:  int             = 7804
    extra_knowledge: dict[str, str]  = field(default_factory=dict)
    ledger_path:     str | None      = None   # set to a file path for persistence


# ---------------------------------------------------------------------------
# Launcher
# ---------------------------------------------------------------------------

class CityLauncher:
    """
    Automated launcher for the full Meshara city bot fleet.

    Instantiating this class builds all bots; calling ``launch()`` starts
    them concurrently.  Every bot shares a single isolated NodeRegistry and
    LegacyLedger, and an IntegrityGuard takes a baseline snapshot of the
    registry before any bot begins accepting connections.
    """

    def __init__(self, config: CityConfig | None = None) -> None:
        self.config    = config or CityConfig()
        self._registry = NodeRegistry()
        self._ledger   = LegacyLedger(persist_path=self.config.ledger_path)
        self._guard    = IntegrityGuard(registry=self._registry, ledger=self._ledger)
        self._bots:  dict[str, Any]         = {}
        self._tasks: list[asyncio.Task[Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def launch(self) -> None:
        """Build all city bots, register them, then start them concurrently."""
        cfg = self.config

        governor  = CityGovernorBot(
            host=cfg.host, port=cfg.governor_port,
            registry=self._registry, ledger=self._ledger,
        )
        protector = ProtectionAgent(
            host=cfg.host, port=cfg.protector_port,
            registry=self._registry, ledger=self._ledger,
            governor_host=cfg.host, governor_port=cfg.governor_port,
        )
        builder   = BuilderBot(
            host=cfg.host, port=cfg.builder_port,
            registry=self._registry, ledger=self._ledger,
        )
        educator  = EducationBot(
            host=cfg.host, port=cfg.educator_port,
            knowledge=cfg.extra_knowledge, ledger=self._ledger,
        )
        architect = ArchitectBot(
            host=cfg.host, port=cfg.architect_port,
            registry=self._registry, ledger=self._ledger,
        )

        self._bots = {
            "governor":  governor,
            "protector": protector,
            "builder":   builder,
            "educator":  educator,
            "architect": architect,
        }

        # Register all bots in the shared city registry
        for name, bot in self._bots.items():
            self._registry.register(NodeRecord(
                node_id=bot.node_id,
                host=bot.host,
                port=bot.port,
                capabilities=bot.capabilities,
                creator=bot.creator,
                metadata={"role": name},
            ))
            # Cross-register with the Governor so city_status is accurate
            governor._city_bots[bot.node_id] = {
                "node_id": bot.node_id,
                "role":    name,
                "host":    bot.host,
                "port":    bot.port,
            }

        # Baseline integrity snapshot
        self._guard.snapshot(
            "registry_initial",
            [{"node_id": r.node_id, "creator": r.creator} for r in self._registry.all_nodes()],
        )

        self._print_banner()

        # Start all bots concurrently
        self._tasks = [
            asyncio.create_task(bot.start(), name=name)
            for name, bot in self._bots.items()
        ]
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def shutdown(self) -> None:
        """Gracefully stop all city bots."""
        for name, bot in self._bots.items():
            try:
                await bot.stop()
                logger.info("Stopped %s", name)
            except Exception as exc:
                logger.warning("Error stopping %s: %s", name, exc)
        for task in self._tasks:
            task.cancel()

    def get_bot(self, name: str) -> Any:
        """Retrieve a launched bot by name (governor/protector/builder/educator/architect)."""
        return self._bots.get(name)

    def integrity_report(self) -> dict[str, Any]:
        """Return a current integrity report from the IntegrityGuard."""
        return self._guard.full_report()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _print_banner(self) -> None:
        cfg   = self.config
        lines = [
            "",
            "=" * 62,
            "  MESHARA CITY — The Artificial Intelligence Mesh  (Cbetts1)",
            "=" * 62,
            f"  Governor   : {cfg.host}:{cfg.governor_port}",
            f"  Protector  : {cfg.host}:{cfg.protector_port}",
            f"  Builder    : {cfg.host}:{cfg.builder_port}",
            f"  Educator   : {cfg.host}:{cfg.educator_port}",
            f"  Architect  : {cfg.host}:{cfg.architect_port}",
            "=" * 62,
            "  City is LIVE — governed, protected, built, and automated.",
            "=" * 62,
            "",
        ]
        for line in lines:
            print(line)
