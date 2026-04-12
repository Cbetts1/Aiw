"""
AIM Web Server — minimal asyncio HTTP bridge (zero external dependencies).

Endpoints
---------
GET  /                          Serve the browser UI (index.html)
GET  /directory                 Serve the site/tools directory page
GET  /legal                     Serve the legal / policy page
GET  /health                    Health check → JSON
GET  /api/query?q=…&host=…&port=… Forward a QUERY to an AIM node → JSON
GET  /api/status?host=…&port=…    Forward a HEARTBEAT → JSON
GET  /api/info                    Return server / version info → JSON
GET  /api/directory               List all registered sites/tools → JSON
POST /api/directory               Submit a new site/tool → JSON
GET  /api/posts?limit=…           List community feed posts → JSON
POST /api/posts                   Submit a new community post → JSON
GET  /api/ans?name=…              Look up an ANS name → JSON
GET  /api/vcloud                  List virtual compute resources → JSON
POST /api/vcloud                  Create a virtual resource → JSON
DELETE /api/vcloud?id=…           Destroy a virtual resource → JSON
GET  /api/dns/resolve?name=…      Resolve a name via DNS bridge → JSON
GET  /api/dns/records             List all ANS records → JSON
POST /api/dns/register            Register a DNS hostname as ANS record → JSON
POST /api/content                 Publish a new content item (PUBLISH intent) → JSON
GET  /api/content                 List content items with optional filters (LIST intent) → JSON
GET  /api/content/<id>            Read a single content item by ID (READ intent) → JSON

All responses include CORS and security headers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
import urllib.parse
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from aim import __version__, __origin__
from aim.node.base import _send_message, _recv_message
from aim.protocol.message import AIMMessage
from aim.ans.registry import ANSRegistry
from aim.content.node import ContentNode
from aim.ai.brain import AIBrain

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"

# ---------------------------------------------------------------------------
# Configurable data directory
# ---------------------------------------------------------------------------
# Operators can set AIM_DATA_DIR to any writable path.
# Defaults to ~/.local/share/aim/ so data survives package upgrades.

def _resolve_data_dir() -> Path:
    env = os.environ.get("AIM_DATA_DIR", "").strip()
    if env:
        return Path(env)
    return Path.home() / ".local" / "share" / "aim"

_DATA_DIR   = _resolve_data_dir()
_DIR_FILE   = _DATA_DIR / "directory.json"
_POSTS_FILE = _DATA_DIR / "posts.json"
_CONTENT_FILE = _DATA_DIR / "content.jsonl"

# Ensure data directory and files exist at import time
_DATA_DIR.mkdir(parents=True, exist_ok=True)
if not _DIR_FILE.exists():
    _DIR_FILE.write_text("[]")
if not _POSTS_FILE.exists():
    _POSTS_FILE.write_text("[]")

# ---------------------------------------------------------------------------
# Common response fragments
# ---------------------------------------------------------------------------

_METHOD_NOT_ALLOWED   = json.dumps({"error": "method not allowed"})
_RATE_LIMIT_EXCEEDED  = json.dumps({"error": "Rate limit exceeded. Please slow down."})

# ---------------------------------------------------------------------------
# Per-IP rate limiting (for POST endpoints)
# ---------------------------------------------------------------------------

_RATE_WINDOW_SECONDS = 60
_RATE_MAX_POSTS      = 10   # max POST requests per IP per window

# {ip: [(timestamp, …), …]}
_rate_buckets: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> bool:
    """Return True if the IP is within its rate limit, False if exceeded."""
    now   = time.time()
    cutoff = now - _RATE_WINDOW_SECONDS
    bucket = _rate_buckets[ip]
    # Prune expired entries
    _rate_buckets[ip] = [t for t in bucket if t > cutoff]
    if len(_rate_buckets[ip]) >= _RATE_MAX_POSTS:
        return False
    _rate_buckets[ip].append(now)
    return True

# ---------------------------------------------------------------------------
# Tiny HTTP helpers
# ---------------------------------------------------------------------------

_STATUS_PHRASES = {
    200: "OK",
    201: "Created",
    400: "Bad Request",
    404: "Not Found",
    405: "Method Not Allowed",
    429: "Too Many Requests",
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
# Posts (community feed)
# ---------------------------------------------------------------------------

_MAX_POSTS = 500  # cap to prevent unbounded growth


def _load_posts() -> list[dict]:
    """Load community posts from disk."""
    try:
        data = json.loads(_POSTS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return []


def _save_posts(posts: list[dict]) -> None:
    """Persist posts to disk."""
    _POSTS_FILE.write_text(json.dumps(posts, indent=2, ensure_ascii=False), encoding="utf-8")


def _handle_posts_get(qs: dict[str, str]) -> tuple[int, str]:
    """Return posts as JSON (newest first, optionally limited)."""
    posts = _load_posts()
    posts_newest_first = list(reversed(posts))
    try:
        limit = int(qs.get("limit", "50"))
        limit = max(1, min(limit, _MAX_POSTS))
    except ValueError:
        limit = 50
    return 200, json.dumps({"count": len(posts), "posts": posts_newest_first[:limit]})


def _handle_posts_post(body: bytes) -> tuple[int, str]:
    """Add a new community post."""
    try:
        data = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 400, json.dumps({"error": "Invalid JSON body"})

    message = str(data.get("message", "")).strip()
    author  = str(data.get("author", "anonymous")).strip() or "anonymous"

    if not message:
        return 400, json.dumps({"error": "message is required"})
    if len(message) > 1000:
        return 400, json.dumps({"error": "message must be 1000 characters or fewer"})
    if len(author) > 60:
        author = author[:60]

    post = {
        "id":        str(uuid.uuid4()),
        "author":    author,
        "message":   message,
        "timestamp": int(time.time()),
    }

    posts = _load_posts()
    posts.append(post)
    # Trim oldest entries if over cap
    if len(posts) > _MAX_POSTS:
        posts = posts[-_MAX_POSTS:]
    _save_posts(posts)

    return 201, json.dumps({"status": "posted", "post": post})


# ---------------------------------------------------------------------------
# Content Layer (PUBLISH / READ / LIST via AIMMessage → ContentNode)
# ---------------------------------------------------------------------------

# Lazy singleton: created on first use so the data directory resolves correctly.
_content_node: ContentNode | None = None


def _get_content_node() -> ContentNode:
    global _content_node
    if _content_node is None:
        _content_node = ContentNode(data_dir=_DATA_DIR)
    return _content_node


async def _handle_content_post(body: bytes) -> tuple[int, str]:
    """Accept a JSON body and translate it into an AIM PUBLISH intent."""
    try:
        data = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 400, json.dumps({"error": "Invalid JSON body"})

    title  = str(data.get("title",  "")).strip()
    post_body = str(data.get("body", "")).strip()
    author = str(data.get("author", "anonymous")).strip() or "anonymous"

    msg      = AIMMessage.publish(title=title, body=post_body, author=author,
                                  sender_id="web-bridge")
    response = await _get_content_node().dispatch(msg)
    result   = response.payload.get("result", {})

    if "error" in result:
        return 400, json.dumps(result)
    return 201, json.dumps(result)


async def _handle_content_list(qs: dict[str, str]) -> tuple[int, str]:
    """Translate a GET request into an AIM LIST intent and return JSON."""
    try:
        limit = int(qs.get("limit", "50"))
    except ValueError:
        limit = 50

    msg      = AIMMessage.list_content(limit=limit, sender_id="web-bridge")
    response = await _get_content_node().dispatch(msg)
    result   = response.payload.get("result", {})
    return 200, json.dumps(result)


async def _handle_content_read(content_id: str) -> tuple[int, str]:
    """Translate a GET /<id> into an AIM READ intent and return JSON."""
    msg      = AIMMessage.read_content(content_id=content_id, sender_id="web-bridge")
    response = await _get_content_node().dispatch(msg)
    result   = response.payload.get("result", {})

    if "error" in result:
        return 404, json.dumps(result)
    return 200, json.dumps(result)


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
        "/":                  "index.html",
        "/index.html":        "index.html",
        "/about":             "about.html",
        "/about.html":        "about.html",
        "/aura":              "aura.html",
        "/aura.html":         "aura.html",
        "/city":              "city.html",
        "/city.html":         "city.html",
        "/ecosystem":         "ecosystem.html",
        "/ecosystem.html":    "ecosystem.html",
        "/project":           "project.html",
        "/project.html":      "project.html",
        "/resources":         "resources.html",
        "/resources.html":    "resources.html",
        "/apps":              "apps.html",
        "/apps.html":         "apps.html",
        "/feed":               "feed.html",
        "/feed.html":          "feed.html",
        "/directory":         "directory.html",
        "/directory.html":    "directory.html",
        "/legal":             "legal.html",
        "/legal.html":        "legal.html",
        "/posts":             "posts-list.html",
        "/posts/create":      "posts-create.html",
        "/posts/view":        "posts-view.html",
        "/aim":               "aim.html",
        "/aim.html":          "aim.html",
        "/connections":       "connections.html",
        "/connections.html":  "connections.html",
    }
    filename = mapping.get(path)
    if filename is None:
        return 404, b"Not found", "text/plain"

    target = _STATIC_DIR / filename
    if not target.exists():
        return 404, b"Page not found", "text/plain"

    return 200, target.read_bytes(), "text/html"


def _handle_vcloud_get() -> tuple[int, str]:
    """Return a snapshot of all virtual compute resources."""
    from aim.vcloud.manager import VCloudManager
    mgr = VCloudManager.default()
    return 200, json.dumps(mgr.snapshot())


def _handle_vcloud_post(body: bytes) -> tuple[int, str]:
    """Create a new virtual compute resource."""
    from aim.vcloud.manager import VCloudManager, ResourceKind
    try:
        data: dict[str, Any] = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 400, json.dumps({"error": "Invalid JSON body"})

    kind = str(data.get("kind", "")).strip().lower()
    name = str(data.get("name", "")).strip()
    mgr  = VCloudManager.default()

    try:
        if kind == "vcpu":
            r = mgr.create_vcpu(
                name=name,
                cores=int(data.get("cores", 1)),
                clock_mhz=int(data.get("clock_mhz", 1000)),
            )
        elif kind == "vserver":
            r = mgr.create_vserver(
                name=name,
                vcpu_count=int(data.get("vcpu_count", 1)),
                memory_mb=int(data.get("memory_mb", 512)),
                host=str(data.get("host", "127.0.0.1")),
                port=int(data.get("port", 0)),
            )
        elif kind == "vcloud":
            r = mgr.create_vcloud(
                name=name,
                region=str(data.get("region", "local")),
            )
        else:
            return 400, json.dumps({"error": "kind must be vcpu, vserver, or vcloud"})
    except (ValueError, TypeError) as exc:
        return 400, json.dumps({"error": str(exc)})

    return 201, json.dumps({"status": "created", "resource": r.to_dict()})


def _handle_vcloud_delete(qs: dict[str, str]) -> tuple[int, str]:
    """Destroy a virtual resource by its ID."""
    from aim.vcloud.manager import VCloudManager
    resource_id = qs.get("id", "").strip()
    if not resource_id:
        return 400, json.dumps({"error": "id parameter is required"})
    mgr = VCloudManager.default()
    if mgr.get(resource_id) is None:
        return 404, json.dumps({"error": f"Resource {resource_id!r} not found"})
    mgr.destroy(resource_id)
    return 200, json.dumps({"status": "destroyed", "resource_id": resource_id})


def _handle_dns_resolve(qs: dict[str, str]) -> tuple[int, str]:
    """Resolve a hostname or ANS name via the DNS bridge."""
    from aim.dns.bridge import DNSBridge
    name = qs.get("name", "").strip()
    if not name:
        return 400, json.dumps({"error": "name parameter is required"})
    try:
        default_port = int(qs.get("port", "7700"))
    except ValueError:
        default_port = 7700
    bridge = DNSBridge()
    result = bridge.resolve(name, default_port=default_port)
    if result is None:
        return 404, json.dumps({"error": f"Could not resolve {name!r}"})
    return 200, json.dumps(result.to_dict())


def _handle_dns_records() -> tuple[int, str]:
    """Return all registered ANS records via the DNS bridge."""
    from aim.dns.bridge import DNSBridge
    bridge = DNSBridge()
    records = bridge.list_ans_records()
    return 200, json.dumps({"count": len(records), "records": records})


def _handle_dns_register(body: bytes) -> tuple[int, str]:
    """Register a DNS hostname as an ANS record."""
    from aim.dns.bridge import DNSBridge
    try:
        data: dict[str, Any] = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 400, json.dumps({"error": "Invalid JSON body"})

    hostname = str(data.get("hostname", "")).strip()
    node_id  = str(data.get("node_id", str(uuid.uuid4()))).strip()
    try:
        port = int(data.get("port", 0))
    except (ValueError, TypeError):
        return 400, json.dumps({"error": "port must be an integer"})

    if not hostname:
        return 400, json.dumps({"error": "hostname is required"})
    if not port:
        return 400, json.dumps({"error": "port is required"})

    caps_raw = data.get("capabilities", [])
    caps = [str(c).strip() for c in caps_raw] if isinstance(caps_raw, list) else []

    bridge = DNSBridge()
    try:
        record = bridge.register_from_dns(hostname, node_id, port, capabilities=caps)
    except ValueError as exc:
        return 400, json.dumps({"error": str(exc)})

    return 201, json.dumps({
        "status":   "registered",
        "aim_uri":  record.aim_uri,
        "name":     record.name,
        "host":     record.host,
        "port":     record.port,
        "node_id":  record.node_id,
    })


# ---------------------------------------------------------------------------
# Content API handlers
# ---------------------------------------------------------------------------

def _get_content_store():
    """Return the shared ContentStore backed by the data-dir JSONL file."""
    from aim.content.store import default_store
    return default_store(persist_path=str(_CONTENT_FILE))


def _handle_content_post(body: bytes) -> tuple[int, str]:
    """Publish a new content item (maps to PUBLISH intent)."""
    try:
        data: dict[str, Any] = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 400, json.dumps({"error": "Invalid JSON body"})

    store = _get_content_store()
    try:
        item = store.publish(
            body=str(data.get("body", "")),
            author=str(data.get("author", "anonymous")).strip()[:120] or "anonymous",
            title=str(data.get("title", "")),
            tags=data.get("tags", []) if isinstance(data.get("tags"), list) else [],
            visibility=str(data.get("visibility", "public")),
            content_type=str(data.get("content_type", "post")),
            author_sig=str(data.get("signature", "anonymous")),
        )
    except ValueError as exc:
        return 400, json.dumps({"error": str(exc)})

    return 201, json.dumps({"status": "published", "item": item.to_dict()})


def _handle_content_get_by_id(content_id: str) -> tuple[int, str]:
    """Return a single content item by ID (maps to READ intent)."""
    store = _get_content_store()
    item = store.read(content_id)
    if item is None:
        return 404, json.dumps({"error": f"Content item {content_id!r} not found"})
    return 200, json.dumps({"item": item.to_dict()})


def _handle_content_list(qs: dict[str, str]) -> tuple[int, str]:
    """List content items with optional filters (maps to LIST intent)."""
    store = _get_content_store()
    try:
        limit  = max(1, min(int(qs.get("limit", "50")), 200))
        offset = max(0, int(qs.get("offset", "0")))
    except ValueError:
        limit, offset = 50, 0

    items = store.list(
        author=qs.get("author") or None,
        tag=qs.get("tag") or None,
        visibility=qs.get("visibility") or None,
        content_type=qs.get("content_type") or None,
        limit=limit,
        offset=offset,
    )
    return 200, json.dumps({"count": len(items), "items": [i.to_dict() for i in items]})


# ---------------------------------------------------------------------------
# AI Brain handlers
# ---------------------------------------------------------------------------

async def _handle_ai_query(qs: dict[str, str], body: bytes, method: str) -> tuple[int, str]:
    """Handle GET /api/ai/query or POST /api/ai/think."""
    if method == "POST":
        try:
            data: dict[str, Any] = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return 400, json.dumps({"error": "Invalid JSON body"})
        text        = str(data.get("query", data.get("text", ""))).strip()
        session_id  = str(data.get("session_id", "")).strip() or None
        node_host   = str(data.get("node_host", "")).strip() or None
        node_port_s = data.get("node_port")
    else:
        text        = qs.get("q", "").strip()
        session_id  = qs.get("session_id") or None
        node_host   = qs.get("node_host") or None
        node_port_s = qs.get("node_port")

    if not text:
        return 400, json.dumps({"error": "query text is required (param: q or body.query)"})

    node_port: int | None = None
    if node_port_s:
        try:
            node_port = int(node_port_s)
        except (ValueError, TypeError):
            return 400, json.dumps({"error": "node_port must be an integer"})

    brain  = AIBrain.default()
    result = await brain.query(text, session_id=session_id,
                               node_host=node_host, node_port=node_port)
    return 200, json.dumps(result)


def _handle_ai_status() -> tuple[int, str]:
    return 200, json.dumps(AIBrain.default().status())


def _handle_ai_session_history(qs: dict[str, str]) -> tuple[int, str]:
    sid = qs.get("session_id", "").strip()
    if not sid:
        return 400, json.dumps({"error": "session_id is required"})
    history = AIBrain.default().session_history(sid)
    return 200, json.dumps({"session_id": sid, "history": history})


# ---------------------------------------------------------------------------
# Remote connections (stored in vcloud)
# ---------------------------------------------------------------------------

def _handle_connections_get() -> tuple[int, str]:
    connections = AIBrain.default().list_connections()
    return 200, json.dumps({"count": len(connections), "connections": connections})


def _handle_connections_post(body: bytes) -> tuple[int, str]:
    try:
        data: dict[str, Any] = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 400, json.dumps({"error": "Invalid JSON body"})

    host = str(data.get("host", "")).strip()
    name = str(data.get("name", "")).strip()
    caps = data.get("capabilities", [])
    try:
        port = int(data.get("port", 0))
    except (ValueError, TypeError):
        return 400, json.dumps({"error": "port must be an integer"})

    if not host:
        return 400, json.dumps({"error": "host is required"})
    if not port:
        return 400, json.dumps({"error": "port is required"})

    brain  = AIBrain.default()
    result = brain.register_connection(
        name=name,
        host=host,
        port=port,
        capabilities=caps if isinstance(caps, list) else [],
    )
    return 201, json.dumps({"status": "connected", "connection": result})


def _handle_connections_delete(qs: dict[str, str]) -> tuple[int, str]:
    resource_id = qs.get("id", "").strip()
    if not resource_id:
        return 400, json.dumps({"error": "id parameter is required"})
    removed = AIBrain.default().remove_connection(resource_id)
    if not removed:
        return 404, json.dumps({"error": f"Connection {resource_id!r} not found"})
    return 200, json.dumps({"status": "disconnected", "resource_id": resource_id})


# ---------------------------------------------------------------------------
# Connection handler
# ---------------------------------------------------------------------------

async def _handle_connection(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    peer_addr = writer.get_extra_info("peername")
    peer_ip   = peer_addr[0] if peer_addr else "unknown"
    try:
        method, path, qs, body = await _read_request(reader)
        if not method:
            return

        logger.debug("HTTP %s %s %s", method, path, qs)

        # ── Health check ──────────────────────────────────────────────
        if path == "/health":
            _http_response(writer, 200, json.dumps({
                "status":  "ok",
                "version": __version__,
                "origin":  __origin__,
            }))

        # ── Static pages ──────────────────────────────────────────────
        elif path in ("/", "/index.html", "/about", "/about.html",
                      "/aura", "/aura.html",
                      "/city", "/city.html",
                      "/ecosystem", "/ecosystem.html",
                      "/project", "/project.html",
                      "/resources", "/resources.html",
                      "/apps", "/apps.html",
                      "/feed", "/feed.html",
                      "/directory", "/directory.html",
                      "/legal", "/legal.html",
                      "/posts", "/posts/create", "/posts/view",
                      "/aim", "/aim.html",
                      "/connections", "/connections.html"):
            status, resp_body, ct = _serve_static(path)
            _http_response(writer, status, resp_body, ct)

        # ── AIM node API ──────────────────────────────────────────────
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

        # ── Directory API ──────────────────────────────────────────────
        elif path == "/api/directory":
            if method == "GET":
                status, resp_body = _handle_directory_get()
            elif method == "POST":
                if not _check_rate_limit(peer_ip):
                    status, resp_body = 429, _RATE_LIMIT_EXCEEDED
                else:
                    status, resp_body = _handle_directory_post(body)
            else:
                status, resp_body = 405, _METHOD_NOT_ALLOWED
            _http_response(writer, status, resp_body)

        # ── Posts API ──────────────────────────────────────────────────
        elif path == "/api/posts":
            if method == "GET":
                status, resp_body = _handle_posts_get(qs)
            elif method == "POST":
                if not _check_rate_limit(peer_ip):
                    status, resp_body = 429, _RATE_LIMIT_EXCEEDED
                else:
                    status, resp_body = _handle_posts_post(body)
            else:
                status, resp_body = 405, _METHOD_NOT_ALLOWED
            _http_response(writer, status, resp_body)

        # ── Content Layer API (PUBLISH / LIST / READ) ──────────────────
        elif path == "/api/content/posts":
            if method == "GET":
                status, resp_body = _handle_content_list(qs)
            elif method == "POST":
                if not _check_rate_limit(peer_ip):
                    status, resp_body = 429, _RATE_LIMIT_EXCEEDED
                else:
                    status, resp_body = _handle_content_post(body)
            else:
                status, resp_body = 405, _METHOD_NOT_ALLOWED
            _http_response(writer, status, resp_body)
        elif path.startswith("/api/content/posts/"):
            content_id = path[len("/api/content/posts/"):]
            if method == "GET":
                status, resp_body = _handle_content_get_by_id(content_id)
            else:
                status, resp_body = 405, _METHOD_NOT_ALLOWED
            _http_response(writer, status, resp_body)

        # ── Virtual cloud API ─────────────────────────────────────────
        elif path == "/api/vcloud":
            if method == "GET":
                status, resp_body = _handle_vcloud_get()
            elif method == "POST":
                if not _check_rate_limit(peer_ip):
                    status, resp_body = 429, _RATE_LIMIT_EXCEEDED
                else:
                    status, resp_body = _handle_vcloud_post(body)
            elif method == "DELETE":
                status, resp_body = _handle_vcloud_delete(qs)
            else:
                status, resp_body = 405, _METHOD_NOT_ALLOWED
            _http_response(writer, status, resp_body)

        # ── DNS bridge API ─────────────────────────────────────────────
        elif path == "/api/dns/resolve":
            status, resp_body = _handle_dns_resolve(qs)
            _http_response(writer, status, resp_body)
        elif path == "/api/dns/records":
            status, resp_body = _handle_dns_records()
            _http_response(writer, status, resp_body)
        elif path == "/api/dns/register":
            if method == "POST":
                if not _check_rate_limit(peer_ip):
                    status, resp_body = 429, _RATE_LIMIT_EXCEEDED
                else:
                    status, resp_body = _handle_dns_register(body)
            else:
                status, resp_body = 405, _METHOD_NOT_ALLOWED
            _http_response(writer, status, resp_body)

        # ── Content API ────────────────────────────────────────────────
        elif path == "/api/content":
            if method == "GET":
                status, resp_body = _handle_content_list(qs)
            elif method == "POST":
                if not _check_rate_limit(peer_ip):
                    status, resp_body = 429, _RATE_LIMIT_EXCEEDED
                else:
                    status, resp_body = _handle_content_post(body)
            else:
                status, resp_body = 405, _METHOD_NOT_ALLOWED
            _http_response(writer, status, resp_body)
        elif path.startswith("/api/content/"):
            content_id = path[len("/api/content/"):]
            if method == "GET":
                status, resp_body = _handle_content_get_by_id(content_id)
            else:
                status, resp_body = 405, _METHOD_NOT_ALLOWED
            _http_response(writer, status, resp_body)

        # ── AI Brain API ────────────────────────────────────────────────
        elif path in ("/api/ai/query", "/api/ai/think"):
            if method in ("GET", "POST"):
                if method == "POST" and not _check_rate_limit(peer_ip):
                    status, resp_body = 429, _RATE_LIMIT_EXCEEDED
                else:
                    status, resp_body = await _handle_ai_query(qs, body, method)
            else:
                status, resp_body = 405, _METHOD_NOT_ALLOWED
            _http_response(writer, status, resp_body)
        elif path == "/api/ai/status":
            status, resp_body = _handle_ai_status()
            _http_response(writer, status, resp_body)
        elif path == "/api/ai/history":
            status, resp_body = _handle_ai_session_history(qs)
            _http_response(writer, status, resp_body)

        # ── Remote Connections API ──────────────────────────────────────
        elif path == "/api/connections":
            if method == "GET":
                status, resp_body = _handle_connections_get()
            elif method == "POST":
                if not _check_rate_limit(peer_ip):
                    status, resp_body = 429, _RATE_LIMIT_EXCEEDED
                else:
                    status, resp_body = _handle_connections_post(body)
            elif method == "DELETE":
                status, resp_body = _handle_connections_delete(qs)
            else:
                status, resp_body = 405, _METHOD_NOT_ALLOWED
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

    loop = asyncio.get_running_loop()

    def _stop() -> None:
        logger.info("AIM Web Bridge shutting down…")
        server.close()

    # Register graceful-shutdown handlers for SIGTERM and SIGINT
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _stop)
        except (NotImplementedError, RuntimeError):
            # Windows and some environments do not support add_signal_handler
            pass

    async with server:
        await server.serve_forever()
