"""
AIM Web Server — minimal asyncio HTTP bridge (zero external dependencies).

Endpoints
---------
GET /                          Serve the browser UI (index.html)
GET /api/query?q=…&host=…&port=…   Forward a QUERY to an AIM node → JSON
GET /api/status?host=…&port=…      Forward a HEARTBEAT  → JSON
GET /api/info                  Return server / version info → JSON

All responses include CORS headers so the UI can be hosted separately.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.parse
from pathlib import Path

from aim import __version__, __origin__
from aim.node.base import _send_message, _recv_message
from aim.protocol.message import AIMMessage

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"

# ---------------------------------------------------------------------------
# Tiny HTTP helpers
# ---------------------------------------------------------------------------

_STATUS_PHRASES = {
    200: "OK",
    400: "Bad Request",
    404: "Not Found",
    500: "Internal Server Error",
    502: "Bad Gateway",
}


def _http_response(
    writer: asyncio.StreamWriter,
    status: int,
    body: str | bytes,
    content_type: str = "application/json",
) -> None:
    if isinstance(body, str):
        body = body.encode()
    phrase = _STATUS_PHRASES.get(status, "Unknown")
    headers = (
        f"HTTP/1.1 {status} {phrase}\r\n"
        f"Content-Type: {content_type}; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "Connection: close\r\n"
        "\r\n"
    )
    writer.write(headers.encode() + body)


async def _read_request(reader: asyncio.StreamReader) -> tuple[str, str, dict[str, str]]:
    """Parse the first line of an HTTP request.  Returns (method, path, qs_params)."""
    try:
        raw = await asyncio.wait_for(reader.readline(), timeout=10)
    except asyncio.TimeoutError:
        return "", "", {}
    line = raw.decode(errors="replace").strip()
    parts = line.split()
    if len(parts) < 2:
        return "", "", {}
    method, full_path = parts[0], parts[1]
    parsed = urllib.parse.urlparse(full_path)
    qs = dict(urllib.parse.parse_qsl(parsed.query))
    # Drain remaining headers (we don't need them)
    while True:
        try:
            header_line = await asyncio.wait_for(reader.readline(), timeout=5)
        except asyncio.TimeoutError:
            break
        if header_line in (b"\r\n", b"\n", b""):
            break
    return method, parsed.path, qs


# ---------------------------------------------------------------------------
# API handlers
# ---------------------------------------------------------------------------

async def _handle_query(qs: dict[str, str]) -> tuple[int, str]:
    """Forward a QUERY intent to an AIM node and return (status, json_body)."""
    text = qs.get("q", "").strip()
    host = qs.get("host", "127.0.0.1")
    try:
        port = int(qs.get("port", "7700"))
    except ValueError:
        return 400, json.dumps({"error": "port must be an integer"})

    if not text:
        return 400, json.dumps({"error": "q parameter is required"})

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=8
        )
        msg = AIMMessage.query(text, sender_id="web-bridge")
        await _send_message(writer, msg)
        response = await asyncio.wait_for(_recv_message(reader), timeout=10)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
    except (ConnectionRefusedError, OSError):
        return 502, json.dumps({"error": f"Cannot connect to AIM node at {host}:{port}"})
    except asyncio.TimeoutError:
        return 502, json.dumps({"error": f"AIM node at {host}:{port} did not respond in time"})

    if response is None:
        return 502, json.dumps({"error": "Empty response from AIM node"})

    result = response.payload.get("result", response.payload)
    return 200, json.dumps({"query": text, "result": result, "node": f"{host}:{port}"})


async def _handle_status(qs: dict[str, str]) -> tuple[int, str]:
    """Send a HEARTBEAT to an AIM node and return (status, json_body)."""
    host = qs.get("host", "127.0.0.1")
    try:
        port = int(qs.get("port", "7700"))
    except ValueError:
        return 400, json.dumps({"error": "port must be an integer"})

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=8
        )
        msg = AIMMessage.heartbeat(sender_id="web-bridge")
        await _send_message(writer, msg)
        response = await asyncio.wait_for(_recv_message(reader), timeout=10)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
    except (ConnectionRefusedError, OSError):
        return 502, json.dumps({"online": False, "error": f"Cannot connect to {host}:{port}"})
    except asyncio.TimeoutError:
        return 502, json.dumps({"online": False, "error": "Timeout"})

    if response is None:
        return 502, json.dumps({"online": False, "error": "No response"})

    return 200, json.dumps({"online": True, "node": f"{host}:{port}",
                             "result": response.payload.get("result", {})})


def _handle_info() -> tuple[int, str]:
    return 200, json.dumps({
        "name": "AIM Web Bridge",
        "version": __version__,
        "origin": __origin__,
    })


def _serve_static(path: str) -> tuple[int, bytes, str]:
    """Return (status, body_bytes, content_type) for a static file request."""
    # Only serve index.html from the static directory
    if path in ("/", "/index.html", ""):
        target = _STATIC_DIR / "index.html"
    else:
        return 404, b"Not found", "text/plain"

    if not target.exists():
        return 404, b"UI not found", "text/plain"

    return 200, target.read_bytes(), "text/html"


# ---------------------------------------------------------------------------
# Connection handler
# ---------------------------------------------------------------------------

async def _handle_connection(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    try:
        method, path, qs = await _read_request(reader)
        if not method:
            return

        logger.debug("HTTP %s %s %s", method, path, qs)

        if path in ("/", "/index.html"):
            status, body, ct = _serve_static(path)
            _http_response(writer, status, body, ct)
        elif path == "/api/query":
            status, body = await _handle_query(qs)
            _http_response(writer, status, body)
        elif path == "/api/status":
            status, body = await _handle_status(qs)
            _http_response(writer, status, body)
        elif path == "/api/info":
            status, body = _handle_info()
            _http_response(writer, status, body)
        else:
            _http_response(writer, 404, json.dumps({"error": "not found"}))

        await writer.drain()
    except Exception:
        logger.exception("Error handling HTTP connection")
    finally:
        writer.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def start_web_server(host: str = "0.0.0.0", port: int = 8080) -> None:
    """Start the AIM web bridge and serve until interrupted."""
    server = await asyncio.start_server(_handle_connection, host, port)
    addr = server.sockets[0].getsockname()
    logger.info("AIM Web Bridge listening on http://%s:%s", addr[0], addr[1])
    print(f"\n{'='*60}")
    print(f"  AIM Web Bridge  v{__version__}")
    print(f"  Origin creator : {__origin__}")
    print(f"  Open in browser: http://{addr[0]}:{addr[1]}")
    print(f"  (Use http://localhost:{addr[1]} on this machine)")
    print(f"{'='*60}\n")
    async with server:
        await server.serve_forever()
