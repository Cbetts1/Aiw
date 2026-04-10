"""
AIM CLI — command-line entry point for starting and interacting with nodes.

Usage
-----
    # Start a single agent node on the default port
    aim node start

    # Start on a specific port
    aim node start --port 7701

    # Query a running node
    aim query "What is the AIM mesh?" --host 127.0.0.1 --port 7700

    # Show mesh status
    aim status
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from aim import __version__, __origin__
from aim.node.agent import AgentNode
from aim.node.registry import NodeRegistry, NodeRecord
from aim.protocol.message import AIMMessage, Intent
from aim.identity.signature import CreatorSignature
from aim.identity.ledger import default_ledger, EventKind


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def _cmd_node_start(args: argparse.Namespace) -> None:
    sig = CreatorSignature()
    node = AgentNode(
        host=args.host,
        port=args.port,
        capabilities=args.capabilities.split(",") if args.capabilities else ["query", "task"],
    )

    # Register in local registry
    registry = NodeRegistry.default()
    registry.register(NodeRecord(
        node_id=node.node_id,
        host=node.host,
        port=node.port,
        capabilities=node.capabilities,
        creator=node.creator,
    ))

    # Record in legacy ledger
    ledger = default_ledger()
    ledger.record(EventKind.NODE_CREATED, node.node_id, payload={"host": args.host, "port": args.port}, signature=sig)

    print(f"\n{'='*60}")
    print(f"  AIM — Artificial Intelligence Mesh  v{__version__}")
    print(f"  Origin creator : {__origin__}")
    print(f"  Node ID        : {node.node_id}")
    print(f"  Address        : {args.host}:{args.port}")
    print(f"  Signature      : {sig}")
    print(f"{'='*60}\n")

    # Announce to seed peers if given
    if args.peers:
        for peer_str in args.peers.split(","):
            peer_str = peer_str.strip()
            if ":" in peer_str:
                peer_host, peer_port_str = peer_str.rsplit(":", 1)
                try:
                    peer_port = int(peer_port_str)
                    await node.announce_to(peer_host, peer_port)
                except ValueError:
                    pass

    try:
        await node.start()
    except KeyboardInterrupt:
        await node.stop()
        ledger.record(EventKind.NODE_STOPPED, node.node_id)


async def _cmd_query(args: argparse.Namespace) -> None:
    msg = AIMMessage.query(args.text, sender_id="cli")
    reader, writer = await asyncio.open_connection(args.host, args.port)
    from aim.node.base import _send_message, _recv_message
    await _send_message(writer, msg)
    response = await _recv_message(reader)
    writer.close()
    if response:
        result = response.payload.get("result", response.payload)
        print(json.dumps(result, indent=2))
    else:
        print("No response received.", file=sys.stderr)


async def _cmd_city_start(args: argparse.Namespace) -> None:
    from aim.city.launcher import CityLauncher, CityConfig

    config = CityConfig(
        host=args.host,
        governor_port=args.governor_port,
        protector_port=args.protector_port,
        builder_port=args.builder_port,
        educator_port=args.educator_port,
        architect_port=args.architect_port,
        ledger_path=args.ledger or None,
    )
    launcher = CityLauncher(config)
    try:
        await launcher.launch()
    except KeyboardInterrupt:
        await launcher.shutdown()


async def _cmd_city_status(args: argparse.Namespace) -> None:
    msg = AIMMessage.task("city_status", {}, sender_id="cli")
    reader, writer = await asyncio.open_connection(args.host, args.port)
    from aim.node.base import _send_message, _recv_message
    await _send_message(writer, msg)
    response = await _recv_message(reader)
    writer.close()
    if response:
        print(json.dumps(response.payload.get("result", response.payload), indent=2))
    else:
        print("Governor did not respond.", file=sys.stderr)



    msg = AIMMessage.heartbeat(sender_id="cli")
    reader, writer = await asyncio.open_connection(args.host, args.port)
    from aim.node.base import _send_message, _recv_message
    await _send_message(writer, msg)
    response = await _recv_message(reader)
    writer.close()
    if response:
        print(json.dumps(response.payload.get("result", {}), indent=2))
    else:
        print("Node did not respond.", file=sys.stderr)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aim",
        description="AIM — Artificial Intelligence Mesh CLI",
    )
    parser.add_argument("--version", action="version", version=f"aim {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true")

    sub = parser.add_subparsers(dest="command")

    # --- node subcommand ---
    node_p = sub.add_parser("node", help="Node management")
    node_sub = node_p.add_subparsers(dest="node_command")

    start_p = node_sub.add_parser("start", help="Start an AIM node")
    start_p.add_argument("--host", default="127.0.0.1")
    start_p.add_argument("--port", type=int, default=7700)
    start_p.add_argument("--capabilities", default="", help="Comma-separated capability tags")
    start_p.add_argument("--peers", default="", help="Comma-separated host:port seed peers")

    # --- query subcommand ---
    query_p = sub.add_parser("query", help="Send a QUERY to a running node")
    query_p.add_argument("text", help="Query text")
    query_p.add_argument("--host", default="127.0.0.1")
    query_p.add_argument("--port", type=int, default=7700)

    # --- status subcommand ---
    status_p = sub.add_parser("status", help="Check if a node is alive")
    status_p.add_argument("--host", default="127.0.0.1")
    status_p.add_argument("--port", type=int, default=7700)

    # --- city subcommand ---
    city_p = sub.add_parser("city", help="AIM city governance commands")
    city_sub = city_p.add_subparsers(dest="city_command")

    city_start_p = city_sub.add_parser("start", help="Start the full AIM city bot fleet")
    city_start_p.add_argument("--host",           default="127.0.0.1")
    city_start_p.add_argument("--governor-port",  type=int, default=7800)
    city_start_p.add_argument("--protector-port", type=int, default=7801)
    city_start_p.add_argument("--builder-port",   type=int, default=7802)
    city_start_p.add_argument("--educator-port",  type=int, default=7803)
    city_start_p.add_argument("--architect-port", type=int, default=7804)
    city_start_p.add_argument("--ledger",         default="", help="Path for persistent ledger file")

    city_status_p = city_sub.add_parser("status", help="Query city status from the Governor")
    city_status_p.add_argument("--host", default="127.0.0.1")
    city_status_p.add_argument("--port", type=int, default=7800)

    # --- web subcommand ---
    web_p = sub.add_parser("web", help="Browser-accessible web bridge")
    web_sub = web_p.add_subparsers(dest="web_command")

    web_start_p = web_sub.add_parser("start", help="Start the AIM web bridge")
    web_start_p.add_argument(
        "--host", default="0.0.0.0",
        help="Interface to listen on (default: 0.0.0.0 — all interfaces)",
    )
    web_start_p.add_argument(
        "--port", type=int, default=8080,
        help="HTTP port to serve the UI on (default: 8080)",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _setup_logging(getattr(args, "verbose", False))

    if args.command == "node" and args.node_command == "start":
        asyncio.run(_cmd_node_start(args))
    elif args.command == "query":
        asyncio.run(_cmd_query(args))
    elif args.command == "status":
        asyncio.run(_cmd_status(args))
    elif args.command == "city" and getattr(args, "city_command", None) == "start":
        asyncio.run(_cmd_city_start(args))
    elif args.command == "city" and getattr(args, "city_command", None) == "status":
        asyncio.run(_cmd_city_status(args))
    elif args.command == "web" and getattr(args, "web_command", None) == "start":
        from aim.web.server import start_web_server
        asyncio.run(start_web_server(host=args.host, port=args.port))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
