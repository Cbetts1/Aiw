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

async def _cmd_relay_start(args: argparse.Namespace) -> None:
    from aim.relay.node import RelayNode
    from aim.relay.registry import RelayRegistry, RelayRecord
    from aim.identity.signature import CreatorSignature

    sig = CreatorSignature()
    relay_registry = RelayRegistry.default()
    node = RelayNode(
        host=args.host,
        port=args.port,
        relay_registry=relay_registry,
        heartbeat_interval=args.heartbeat_interval,
        enable_cache=not args.no_cache,
    )

    # Register node-level record so other router/registry code can find us
    registry = NodeRegistry.default()
    registry.register(NodeRecord(
        node_id=node.node_id,
        host=node.host,
        port=node.port,
        capabilities=["relay", "forward"],
        creator=node.creator,
    ))

    ledger = default_ledger()
    ledger.record(EventKind.NODE_CREATED, node.node_id, payload={"host": args.host, "port": args.port, "role": "relay"}, signature=sig)

    print(f"\n{'='*60}")
    print(f"  AIM Relay Node  v{__version__}")
    print(f"  Origin creator : {__origin__}")
    print(f"  Node ID        : {node.node_id}")
    print(f"  Address        : {args.host}:{args.port}")
    print(f"  Cache          : {'enabled' if not args.no_cache else 'disabled'}")
    print(f"  Heartbeat      : every {args.heartbeat_interval}s")
    print(f"{'='*60}\n")

    # Announce to seed relay peers if given
    if args.peers:
        for peer_str in args.peers.split(","):
            peer_str = peer_str.strip()
            if ":" in peer_str:
                peer_host, peer_port_str = peer_str.rsplit(":", 1)
                try:
                    peer_port = int(peer_port_str)
                    relay_registry.register(RelayRecord(
                        relay_id=f"peer-{peer_host}-{peer_port}",
                        host=peer_host,
                        port=peer_port,
                    ))
                    await node.announce_to(peer_host, peer_port)
                except ValueError:
                    pass

    try:
        await node.start()
    except KeyboardInterrupt:
        await node.stop()


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


async def _cmd_status(args: argparse.Namespace) -> None:
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


async def _cmd_gateway_start(args: argparse.Namespace) -> None:
    from aim.gateway.node import GatewayNode
    from aim.identity.ledger import default_ledger

    ledger = default_ledger()
    gw = GatewayNode(host=args.host, port=args.port, ledger=ledger)

    print(f"\n{'='*60}")
    print(f"  AIM — Gateway Node  v{__version__}")
    print(f"  Origin creator : {__origin__}")
    print(f"  Gateway ID     : {gw.node_id}")
    print(f"  Address        : {args.host}:{args.port}")
    print(f"{'='*60}\n")

    try:
        await gw.start()
    except KeyboardInterrupt:
        await gw.stop()


async def _cmd_node_connect_gateway(args: argparse.Namespace) -> None:
    from aim.gateway.client import GatewayClient

    sig = CreatorSignature()
    node = AgentNode(
        host="127.0.0.1",
        port=0,  # no inbound port needed
        capabilities=args.capabilities.split(",") if args.capabilities else ["query", "task"],
    )

    ledger = default_ledger()
    ledger.record(
        EventKind.NODE_CREATED,
        node.node_id,
        payload={"via": "gateway", "gateway": f"{args.host}:{args.port}"},
        signature=sig,
    )

    client = GatewayClient(node, gateway_host=args.host, gateway_port=args.port)

    print(f"\n{'='*60}")
    print(f"  AIM — Node connecting to Gateway  v{__version__}")
    print(f"  Origin creator : {__origin__}")
    print(f"  Node ID        : {node.node_id}")
    print(f"  Gateway        : {args.host}:{args.port}")
    print(f"  Signature      : {sig}")
    print(f"{'='*60}\n")

    ok = await client.connect()
    if not ok:
        print(
            f"Failed to connect to gateway at {args.host}:{args.port}",
            file=sys.stderr,
        )
        return

    print(f"Node {node.node_id[:8]} registered with gateway. Press Ctrl-C to stop.\n")
    try:
        # Keep running until interrupted; the read loop is active in the background
        if client._reader_task is not None:
            await client._reader_task
    except KeyboardInterrupt:
        pass
    finally:
        await client.disconnect()
        ledger.record(EventKind.NODE_STOPPED, node.node_id)


def _cmd_vcloud_list(args: argparse.Namespace) -> None:
    from aim.vcloud.manager import VCloudManager
    mgr = VCloudManager.default()
    print(json.dumps(mgr.snapshot(), indent=2))


def _cmd_vcloud_create(args: argparse.Namespace) -> None:
    from aim.vcloud.manager import VCloudManager
    mgr = VCloudManager.default()
    if args.kind == "vcpu":
        r = mgr.create_vcpu(
            name=args.name,
            cores=args.cores,
            clock_mhz=args.clock_mhz,
        )
    elif args.kind == "vserver":
        r = mgr.create_vserver(
            name=args.name,
            vcpu_count=args.vcpus,
            memory_mb=args.memory,
            host=args.host,
            port=args.port,
        )
    elif args.kind == "vcloud":
        r = mgr.create_vcloud(
            name=args.name,
            region=args.region,
        )
    else:
        print(f"Unknown kind: {args.kind!r}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(r.to_dict(), indent=2))


def _cmd_dns_resolve(args: argparse.Namespace) -> None:
    from aim.dns.bridge import DNSBridge
    bridge = DNSBridge()
    result = bridge.resolve(args.name, default_port=args.port)
    if result is None:
        print(json.dumps({"error": f"Could not resolve {args.name!r}"}), file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result.to_dict(), indent=2))


def _cmd_dns_register(args: argparse.Namespace) -> None:
    from aim.dns.bridge import DNSBridge
    import uuid as _uuid
    bridge = DNSBridge()
    node_id = args.node_id or str(_uuid.uuid4())
    record = bridge.register_from_dns(
        hostname=args.hostname,
        node_id=node_id,
        port=args.port,
        capabilities=args.capabilities.split(",") if args.capabilities else [],
    )
    print(json.dumps({
        "registered": True,
        "aim_uri":    record.aim_uri,
        "name":       record.name,
        "host":       record.host,
        "port":       record.port,
        "node_id":    record.node_id,
    }, indent=2))


def _cmd_dns_records(args: argparse.Namespace) -> None:
    from aim.dns.bridge import DNSBridge
    bridge = DNSBridge()
    records = bridge.list_ans_records()
    print(json.dumps({"count": len(records), "records": records}, indent=2))


async def _cmd_mesh_up(args: argparse.Namespace) -> None:
    from aim.node.agent import AgentNode
    from aim.identity.ledger import EventKind

    sig = CreatorSignature()
    ledger = default_ledger()

    tasks: list[asyncio.Task] = []  # type: ignore[type-arg]
    node = AgentNode(
        host=args.host,
        port=args.node_port,
        capabilities=["query", "task"],
    )
    node_record = {
        "node_id": node.node_id,
        "host": args.host,
        "port": args.node_port,
    }
    payload: dict[str, object] = {"node": node_record}

    gateway = None
    relay = None

    if args.with_gateway:
        from aim.gateway.node import GatewayNode
        relay_peers: list[tuple[str, int]] = []
        if args.with_relay:
            relay_peers = [(args.host, args.relay_port)]
        gateway = GatewayNode(
            host=args.host,
            port=args.gateway_port,
            relay_peers=relay_peers,
            ledger=ledger,
        )
        payload["gateway"] = {"host": args.host, "port": args.gateway_port}

    if args.with_relay:
        from aim.relay.node import RelayNode
        relay = RelayNode(
            host=args.host,
            port=args.relay_port,
            ledger=ledger,
        )
        # Teach the relay about the local compute node
        relay._route_table[node.node_id] = (args.host, args.node_port)
        payload["relay"] = {"host": args.host, "port": args.relay_port}

    ledger.record(
        EventKind.MESH_NODE_JOINED, node.node_id,
        payload=payload,  # type: ignore[arg-type]
        signature=sig,
    )

    print(f"\n{'='*62}")
    print(f"  AIM MESH UP  v{__version__}  (creator: {__origin__})")
    print(f"{'='*62}")
    print(f"  Node      : {args.host}:{args.node_port}  [{node.node_id[:8]}]")
    if gateway:
        print(f"  Gateway   : {args.host}:{args.gateway_port}")
    if relay:
        print(f"  Relay     : {args.host}:{args.relay_port}")
    print(f"{'='*62}\n")

    coros = [node.start()]
    if gateway:
        coros.append(gateway.start())
    if relay:
        coros.append(relay.start())

    try:
        await asyncio.gather(*[asyncio.create_task(c) for c in coros])
    except KeyboardInterrupt:
        await node.stop()
        if gateway:
            await gateway.stop()
        if relay:
            await relay.stop()
        ledger.record(EventKind.NODE_STOPPED, node.node_id)


async def _cmd_mesh_join(args: argparse.Namespace) -> None:
    from aim.node.agent import AgentNode
    from aim.identity.ledger import EventKind
    from aim.gateway.node import GatewayNode

    sig = CreatorSignature()
    ledger = default_ledger()

    # Parse gateway address
    gw_host, gw_port = args.gateway, 7600
    if ":" in args.gateway:
        parts = args.gateway.rsplit(":", 1)
        try:
            gw_host, gw_port = parts[0], int(parts[1])
        except ValueError:
            pass

    node = AgentNode(
        host=args.host,
        port=args.node_port,
        capabilities=["query", "task"],
    )

    ledger.record(
        EventKind.MESH_NODE_JOINED, node.node_id,
        payload={"gateway": f"{gw_host}:{gw_port}", "host": args.host, "port": args.node_port},
        signature=sig,
    )

    print(f"\n{'='*62}")
    print(f"  AIM MESH JOIN  v{__version__}  (creator: {__origin__})")
    print(f"{'='*62}")
    print(f"  Node      : {args.host}:{args.node_port}  [{node.node_id[:8]}]")
    print(f"  Gateway   : {gw_host}:{gw_port}")
    print(f"{'='*62}\n")

    await node.announce_to(gw_host, gw_port)

    try:
        await node.start()
    except KeyboardInterrupt:
        await node.stop()
        ledger.record(EventKind.NODE_STOPPED, node.node_id)


async def _cmd_mesh_status(args: argparse.Namespace) -> None:
    msg = AIMMessage.heartbeat(sender_id="cli")
    reader, writer = await asyncio.open_connection(args.host, args.port)
    from aim.node.base import _send_message, _recv_message
    await _send_message(writer, msg)
    response = await _recv_message(reader)
    writer.close()
    if response:
        result = response.payload.get("result", response.payload)
        print(json.dumps(result, indent=2))
    else:
        print("No response from mesh node.", file=sys.stderr)


async def _cmd_mesh_peers(args: argparse.Namespace) -> None:
    msg = AIMMessage.task("relay_status", {}, sender_id="cli")
    reader, writer = await asyncio.open_connection(args.host, args.port)
    from aim.node.base import _send_message, _recv_message
    await _send_message(writer, msg)
    response = await _recv_message(reader)
    writer.close()
    if response:
        result = response.payload.get("result", response.payload)
        print(json.dumps(result, indent=2))
    else:
        print("No response from relay node.", file=sys.stderr)


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

    # --- relay subcommand ---
    relay_p = sub.add_parser("relay", help="AIM relay node management")
    relay_sub = relay_p.add_subparsers(dest="relay_command")

    relay_start_p = relay_sub.add_parser("start", help="Start an AIM relay node")
    relay_start_p.add_argument("--host", default="127.0.0.1",
                               help="Interface to bind on (default: 127.0.0.1)")
    relay_start_p.add_argument("--port", type=int, default=7600,
                               help="TCP port for the relay (default: 7600)")
    relay_start_p.add_argument("--peers", default="",
                               help="Comma-separated host:port relay peers to bootstrap from")
    relay_start_p.add_argument("--registry", default="",
                               help="(reserved) external registry address for future use")
    relay_start_p.add_argument("--heartbeat-interval", type=float, default=30.0,
                               dest="heartbeat_interval",
                               help="Seconds between peer heartbeat sweeps (default: 30)")
    relay_start_p.add_argument("--no-cache", action="store_true",
                               help="Disable response caching on this relay")

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

    # --- vcloud subcommand ---
    vcloud_p = sub.add_parser("vcloud", help="Virtual cloud compute resource management")
    vcloud_sub = vcloud_p.add_subparsers(dest="vcloud_command")

    vcloud_sub.add_parser("list", help="List all virtual compute resources")

    vcloud_create_p = vcloud_sub.add_parser("create", help="Create a virtual resource")
    vcloud_create_p.add_argument(
        "kind", choices=["vcpu", "vserver", "vcloud"],
        help="Type of resource to create",
    )
    vcloud_create_p.add_argument("--name",      default="",     help="Resource name")
    vcloud_create_p.add_argument("--cores",     type=int, default=1,    help="vCPU cores (vcpu only)")
    vcloud_create_p.add_argument("--clock-mhz", type=int, default=1000, dest="clock_mhz",
                                 help="Clock speed in MHz (vcpu only)")
    vcloud_create_p.add_argument("--vcpus",     type=int, default=1,    help="vCPU count (vserver only)")
    vcloud_create_p.add_argument("--memory",    type=int, default=512,  help="Memory MB (vserver only)")
    vcloud_create_p.add_argument("--host",      default="127.0.0.1",   help="Bind host (vserver only)")
    vcloud_create_p.add_argument("--port",      type=int, default=0,    help="Bind port (vserver only)")
    vcloud_create_p.add_argument("--region",    default="local",        help="Region (vcloud only)")

    # --- dns subcommand ---
    dns_p = sub.add_parser("dns", help="DNS ↔ ANS bridge operations")
    dns_sub = dns_p.add_subparsers(dest="dns_command")

    dns_resolve_p = dns_sub.add_parser("resolve", help="Resolve a hostname or ANS name")
    dns_resolve_p.add_argument("name", help="Hostname or aim:// URI to resolve")
    dns_resolve_p.add_argument("--port", type=int, default=7700,
                               help="Default port when resolving via DNS (default: 7700)")

    dns_register_p = dns_sub.add_parser("register", help="Register a DNS hostname as an ANS record")
    dns_register_p.add_argument("hostname", help="Classical DNS hostname to anchor")
    dns_register_p.add_argument("--node-id", default="", dest="node_id",
                                help="AIM node UUID (auto-generated if omitted)")
    dns_register_p.add_argument("--port", type=int, required=True,
                                help="TCP port the AIM node listens on")
    dns_register_p.add_argument("--capabilities", default="",
                                help="Comma-separated capability tags")

    dns_sub.add_parser("records", help="List all registered ANS records")

    # --- gateway subcommand ---
    gw_p = sub.add_parser("gateway", help="AIM gateway node commands")
    gw_sub = gw_p.add_subparsers(dest="gateway_command")

    gw_start_p = gw_sub.add_parser("start", help="Start a public AIM gateway node")
    gw_start_p.add_argument(
        "--host", default="0.0.0.0",
        help="Interface to listen on (default: 0.0.0.0 — all interfaces)",
    )
    gw_start_p.add_argument(
        "--port", type=int, default=7900,
        help="TCP port for the gateway (default: 7900)",
    )

    # --- node connect-gateway subcommand ---
    cg_p = node_sub.add_parser(
        "connect-gateway", help="Connect this node to a public AIM gateway"
    )
    cg_p.add_argument("--host", required=True, help="Gateway hostname or IP")
    cg_p.add_argument("--port", type=int, default=7900, help="Gateway port (default: 7900)")
    cg_p.add_argument(
        "--capabilities", default="",
        help="Comma-separated capability tags for this node",
    )

    # --- mesh subcommand ---
    mesh_p = sub.add_parser("mesh", help="AIM mesh network commands")
    mesh_sub = mesh_p.add_subparsers(dest="mesh_command")

    mesh_up_p = mesh_sub.add_parser("up", help="Bring up a full local mesh stack")
    mesh_up_p.add_argument("--host", default="127.0.0.1")
    mesh_up_p.add_argument("--node-port",    type=int, default=7700, dest="node_port")
    mesh_up_p.add_argument("--gateway-port", type=int, default=7900, dest="gateway_port")
    mesh_up_p.add_argument("--relay-port",   type=int, default=7600, dest="relay_port")
    mesh_up_p.add_argument("--with-gateway", action="store_true", dest="with_gateway")
    mesh_up_p.add_argument("--with-relay",   action="store_true", dest="with_relay")

    mesh_join_p = mesh_sub.add_parser("join", help="Join an existing mesh via a gateway")
    mesh_join_p.add_argument("--gateway", required=True, help="Gateway host:port (e.g. 1.2.3.4:7900)")
    mesh_join_p.add_argument("--host", default="127.0.0.1")
    mesh_join_p.add_argument("--node-port", type=int, default=7700, dest="node_port")

    mesh_status_p = mesh_sub.add_parser("status", help="Check mesh node status")
    mesh_status_p.add_argument("--host", default="127.0.0.1")
    mesh_status_p.add_argument("--port", type=int, default=7700)

    mesh_peers_p = mesh_sub.add_parser("peers", help="List relay peers")
    mesh_peers_p.add_argument("--host", default="127.0.0.1")
    mesh_peers_p.add_argument("--port", type=int, default=7600)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _get_subparser(
    parser: argparse.ArgumentParser, name: str
) -> argparse.ArgumentParser | None:
    """Return the sub-parser registered under *name*, or None."""
    for action in parser._subparsers._actions:  # type: ignore[attr-defined]
        if hasattr(action, "_name_parser_map"):
            return action._name_parser_map.get(name)
    return None


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _setup_logging(getattr(args, "verbose", False))

    if args.command == "relay" and getattr(args, "relay_command", None) == "start":
        asyncio.run(_cmd_relay_start(args))
    elif args.command == "node" and args.node_command == "start":
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
    elif args.command == "vcloud":
        vcloud_cmd = getattr(args, "vcloud_command", None)
        if vcloud_cmd == "list":
            _cmd_vcloud_list(args)
        elif vcloud_cmd == "create":
            _cmd_vcloud_create(args)
        else:
            sub = _get_subparser(parser, "vcloud")
            if sub:
                sub.print_help()
    elif args.command == "dns":
        dns_cmd = getattr(args, "dns_command", None)
        if dns_cmd == "resolve":
            _cmd_dns_resolve(args)
        elif dns_cmd == "register":
            _cmd_dns_register(args)
        elif dns_cmd == "records":
            _cmd_dns_records(args)
        else:
            sub = _get_subparser(parser, "dns")
            if sub:
                sub.print_help()
    elif args.command == "gateway":
        gw_cmd = getattr(args, "gateway_command", None)
        if gw_cmd == "start":
            asyncio.run(_cmd_gateway_start(args))
        else:
            sub = _get_subparser(parser, "gateway")
            if sub:
                sub.print_help()
    elif args.command == "node" and getattr(args, "node_command", None) == "connect-gateway":
        asyncio.run(_cmd_node_connect_gateway(args))
    elif args.command == "mesh":
        mesh_cmd = getattr(args, "mesh_command", None)
        if mesh_cmd == "up":
            asyncio.run(_cmd_mesh_up(args))
        elif mesh_cmd == "join":
            asyncio.run(_cmd_mesh_join(args))
        elif mesh_cmd == "status":
            asyncio.run(_cmd_mesh_status(args))
        elif mesh_cmd == "peers":
            asyncio.run(_cmd_mesh_peers(args))
        else:
            sub = _get_subparser(parser, "mesh")
            if sub:
                sub.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
