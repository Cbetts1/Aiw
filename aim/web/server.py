"""
AIM Web Server — minimal asyncio HTTP bridge (zero external dependencies).

Endpoints
---------
GET  /                          Serve the browser UI (index.html)
GET  /directory                 Serve the site/tools directory page
GET  /legal                     Serve the legal / policy page
GET  /api/query?q=…&host=…&port=… Forward a QUERY to an AIM node → JSON
GET  /api/status?host=…&port=…    Forward a HEARTBEAT → JSON
GET  /api/info                    Return server / version info → JSON
GET  /api/directory               List all registered sites/tools → JSON
POST /api/directory               Submit a new site/tool → JSON

All responses include CORS and security headers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.parse
import uuid
from pathlib import Path

from aim import __version__, __origin__
from aim.node.base import _send_message, _recv_message
from aim.protocol.message import AIMMessage
from aim.ans.registry import ANSRegistry

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"
_DATA_DIR   = Path(__file__).parent / "data"
_DIR_FILE   = _DATA_DIR / "directory.json"

# Ensure data directory and file exist at import time
_DATA_DIR.mkdir(parents=True, exist_ok=True)
if not _DIR_FILE.exists():
    _DIR_FILE.write_text("[]")

# ---------------------------------------------------------------------------
# Tiny HTTP helpers
# ---------------------------------------------------------------------------

_STATUS_PHRASES = {
    200: "OK",
    201: "Created",
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
        "X-Content-Type-Options: nosniff\r\n"
        "X-Frame-Options: DENY\r\n"
        "Content-Security-Policy: default-src 'self'; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline';\r\n"
        "Referrer-Policy: no-referrer\r\n"
        "Connection: close\r\n"
        "\r\n"
    )
    writer.write(headers.encode() + body)


async def _read_request(
    reader: asyncio.StreamReader,
) -> tuple[str, str, dict[str, str], bytes]:
    """Parse an HTTP request.  Returns (method, path, qs_params, body_bytes)."""
    try:
        raw = await asyncio.wait_for(reader.readline(), timeout=10)
    except asyncio.TimeoutError:
        return "", "", {}, b""
    line = raw.decode(errors="replace").strip()
    parts = line.split()
    if len(parts) < 2:
        return "", "", {}, b""
    method, full_path = parts[0], parts[1]
    parsed = urllib.parse.urlparse(full_path)
    qs = dict(urllib.parse.parse_qsl(parsed.query))

    # Read headers, capturing Content-Length
    content_length = 0
    while True:
        try:
            header_line = await asyncio.wait_for(reader.readline(), timeout=5)
        except asyncio.TimeoutError:
            break
        if header_line in (b"\r\n", b"\n", b""):
            break
        decoded = header_line.decode(errors="replace").strip()
        if decoded.lower().startswith("content-length:"):
            try:
                content_length = int(decoded.split(":", 1)[1].strip())
            except ValueError:
                pass

    # Read body (cap at 1 MiB)
    body = b""
    if content_length > 0:
        try:
            body = await asyncio.wait_for(
                reader.read(min(content_length, 1_048_576)), timeout=10
            )
        except asyncio.TimeoutError:
            pass

    return method, parsed.path, qs, body


def _load_directory() -> list[dict]:
    """Load the site/tool directory from disk."""
    try:
        data = json.loads(_DIR_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return []


def _save_directory(entries: list[dict]) -> None:
    """Persist the directory to disk."""
    _DIR_FILE.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


_VALID_CATEGORIES = {"website", "tool", "resource", "app", "service", "other"}


def _handle_directory_get() -> tuple[int, str]:
    """Return the full directory as JSON."""
    entries = _load_directory()
    return 200, json.dumps({"count": len(entries), "entries": entries})


def _handle_directory_post(body: bytes) -> tuple[int, str]:
    """Add a new entry to the directory."""
    try:
        data = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 400, json.dumps({"error": "Invalid JSON body"})

    name = str(data.get("name", "")).strip()
    url  = str(data.get("url",  "")).strip()
    desc = str(data.get("description", "")).strip()
    cat  = str(data.get("category", "other")).strip().lower()
    creator = str(data.get("creator", "anonymous")).strip()

    if not name:
        return 400, json.dumps({"error": "name is required"})
    if not url:
        return 400, json.dumps({"error": "url is required"})
    if not (url.startswith("http://") or url.startswith("https://")):
        return 400, json.dumps({"error": "url must start with http:// or https://"})
    if cat not in _VALID_CATEGORIES:
        cat = "other"
    if len(name) > 120:
        return 400, json.dumps({"error": "name must be 120 characters or fewer"})
    if len(desc) > 500:
        return 400, json.dumps({"error": "description must be 500 characters or fewer"})

    entry = {
        "id":          str(uuid.uuid4()),
        "name":        name,
        "url":         url,
        "description": desc,
        "category":    cat,
        "creator":     creator[:60],
        "added":       int(time.time()),
    }

    entries = _load_directory()
    entries.append(entry)
    _save_directory(entries)

    return 201, json.dumps({"status": "added", "entry": entry})


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
        except OSError:
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
        except OSError:
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


def _handle_ans_get(qs: dict[str, str]) -> tuple[int, str]:
    """Look up an ANS name and return the matching NodeRecord info as JSON."""
    name = qs.get("name", "").strip()
    if not name:
        return 400, json.dumps({"error": "name parameter is required"})
    registry = ANSRegistry.default()
    record = registry.get(name)
    if record is None:
        return 404, json.dumps({"error": f"ANS name '{name}' not found"})
    return 200, json.dumps({
        "name":         record.name,
        "aim_uri":      record.aim_uri,
        "node_id":      record.node_id,
        "host":         record.host,
        "port":         record.port,
        "capabilities": record.capabilities,
        "creator":      record.creator,
        "ttl_seconds":  record.ttl_seconds,
    })


def _serve_static(path: str) -> tuple[int, bytes, str]:
    """Return (status, body_bytes, content_type) for a static file request."""
    mapping: dict[str, str] = {
        "/":              "index.html",
        "/index.html":    "index.html",
        "/about":         "about.html",
        "/about.html":    "about.html",
        "/apps":          "apps.html",
        "/apps.html":     "apps.html",
        "/directory":     "directory.html",
        "/directory.html":"directory.html",
        "/legal":         "legal.html",
        "/legal.html":    "legal.html",
    }
    filename = mapping.get(path)
    if filename is None:
        return 404, b"Not found", "text/plain"

    target = _STATIC_DIR / filename
    if not target.exists():
        return 404, b"Page not found", "text/plain"

    return 200, target.read_bytes(), "text/html"


# ---------------------------------------------------------------------------
# Connection handler
# ---------------------------------------------------------------------------

async def _handle_connection(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    try:
        method, path, qs, body = await _read_request(reader)
        if not method:
            return

        logger.debug("HTTP %s %s %s", method, path, qs)

        if path in ("/", "/index.html", "/about", "/about.html",
                    "/apps", "/apps.html",
                    "/directory", "/directory.html",
                    "/legal", "/legal.html"):
            status, resp_body, ct = _serve_static(path)
            _http_response(writer, status, resp_body, ct)
        elif path == "/api/query":
            status, resp_body = await _handle_query(qs)
            _http_response(writer, status, resp_body)
        elif path == "/api/status":
            status, resp_body = await _handle_status(qs)
            _http_response(writer, status, resp_body)
        elif path == "/api/info":
            status, resp_body = _handle_info()
            _http_response(writer, status, resp_body)
        elif path == "/api/ans":
            status, resp_body = _handle_ans_get(qs)
            _http_response(writer, status, resp_body)
        elif path == "/api/directory":
            if method == "GET":
                status, resp_body = _handle_directory_get()
            elif method == "POST":
                status, resp_body = _handle_directory_post(body)
            else:
                status, resp_body = 400, json.dumps({"error": "method not allowed"})
            _http_response(writer, status, resp_body)
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
