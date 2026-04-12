"""
AIM WWW Publisher — zero external dependencies, self-contained.

Provides:
  publish_static_site(out_dir, aim_url)
      Copies all AIM static HTML pages from the package into ``out_dir`` and,
      if a running AIM web bridge is reachable at ``aim_url``, pulls live
      posts/content/directory data and embeds them as pre-rendered HTML
      fragments.  The result is a fully self-contained static site that any
      traditional web server can host.

  register_with_www(aim_url, site_name, site_url)
      Posts a site registration to the running AIM web bridge's /api/directory
      endpoint, recording the traditional-web URL alongside the AIM entry.
      Returns the directory entry dict on success.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Path to the static HTML files bundled with the package
_STATIC_DIR = Path(__file__).parent.parent / "web" / "static"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_json(url: str, timeout: int = 5) -> dict[str, Any] | None:
    """Fetch *url* and return parsed JSON, or None on any error."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


def _post_json(url: str, payload: dict[str, Any], timeout: int = 5) -> dict[str, Any] | None:
    """POST *payload* as JSON to *url* and return parsed JSON, or None on error."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


def _render_posts_fragment(posts: list[dict[str, Any]]) -> str:
    """Render a list of post dicts into an HTML fragment."""
    if not posts:
        return "<p class='muted'>No posts yet.</p>"
    items = []
    for p in posts:
        author = _escape(str(p.get("author", "anonymous")))
        message = _escape(str(p.get("message", "")))
        ts = int(p.get("timestamp", 0))
        items.append(
            f'<div class="www-post">'
            f'<span class="www-post-author">{author}</span> '
            f'<span class="www-post-body">{message}</span>'
            f'<span class="www-post-ts">{ts}</span>'
            f"</div>"
        )
    return "\n".join(items)


def _render_directory_fragment(entries: list[dict[str, Any]]) -> str:
    """Render directory entries into an HTML fragment."""
    if not entries:
        return "<p class='muted'>No entries yet.</p>"
    items = []
    for e in entries:
        name = _escape(str(e.get("name", "")))
        url = _escape(str(e.get("url", "#")))
        desc = _escape(str(e.get("description", "")))
        cat = _escape(str(e.get("category", "other")))
        items.append(
            f'<div class="www-dir-entry">'
            f'<a href="{url}" target="_blank" rel="noopener noreferrer">{name}</a>'
            f' <span class="www-dir-cat">[{cat}]</span>'
            f'<p class="www-dir-desc">{desc}</p>'
            f"</div>"
        )
    return "\n".join(items)


def _escape(text: str) -> str:
    """Minimal HTML escaping."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# Static site snapshot
# ---------------------------------------------------------------------------

_WWW_WRAPPER = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title} — A.I.M. on the WWW</title>
  <meta name="description" content="A.I.M. (Artificial Intelligence Mesh) — served on the traditional World Wide Web." />
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg: #060a0f; --surface: #0d1117; --border: #21262d;
      --accent: #58a6ff; --text: #e6edf3; --muted: #8b949e;
      --radius: 8px; --font: 'Segoe UI', system-ui, sans-serif;
    }}
    body {{ background: var(--bg); color: var(--text); font-family: var(--font); line-height: 1.6; }}
    .banner {{
      background: var(--surface); border-bottom: 1px solid var(--border);
      padding: 12px 24px; display: flex; align-items: center; gap: 16px;
    }}
    .banner-logo {{ font-weight: 700; font-size: 1.1rem; color: var(--accent); letter-spacing: 2px; }}
    .banner-note {{ font-size: 0.8rem; color: var(--muted); }}
    .content {{ max-width: 860px; margin: 0 auto; padding: 32px 24px; }}
    .www-post {{ background: var(--surface); border: 1px solid var(--border);
                border-radius: var(--radius); padding: 12px 16px; margin-bottom: 8px; }}
    .www-post-author {{ font-weight: 600; color: var(--accent); margin-right: 8px; }}
    .www-post-ts {{ float: right; font-size: 0.75rem; color: var(--muted); }}
    .www-dir-entry {{ background: var(--surface); border: 1px solid var(--border);
                     border-radius: var(--radius); padding: 12px 16px; margin-bottom: 8px; }}
    .www-dir-entry a {{ color: var(--accent); font-weight: 600; text-decoration: none; }}
    .www-dir-cat {{ color: var(--muted); font-size: 0.8rem; }}
    .www-dir-desc {{ color: var(--muted); font-size: 0.9rem; margin-top: 4px; }}
    .muted {{ color: var(--muted); font-size: 0.9rem; }}
    h2 {{ color: var(--text); font-size: 1.3rem; margin: 24px 0 12px; }}
    .aim-frame {{ width: 100%; height: 600px; border: 1px solid var(--border);
                 border-radius: var(--radius); }}
  </style>
</head>
<body>
  <div class="banner">
    <span class="banner-logo">A.I.M.</span>
    <span class="banner-note">Artificial Intelligence Mesh — published to the World Wide Web</span>
  </div>
  <div class="content">
    {body}
  </div>
</body>
</html>
"""


def publish_static_site(
    out_dir: str = "./aim-www-site",
    aim_url: str = "http://127.0.0.1:8080",
) -> None:
    """
    Snapshot the AIM web content into a self-contained static directory.

    Parameters
    ----------
    out_dir  : destination directory (created if absent).
    aim_url  : base URL of a running AIM web bridge to pull live data from.
               If the bridge is unreachable, static pages are still copied.
    """
    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)

    # 1. Copy all bundled static HTML pages
    copied: list[str] = []
    if _STATIC_DIR.is_dir():
        for html_file in _STATIC_DIR.glob("*.html"):
            target = dest / html_file.name
            shutil.copy2(html_file, target)
            copied.append(html_file.name)
            logger.info("Copied %s → %s", html_file.name, target)

    # 2. Try to pull live data from the running AIM bridge
    aim_url = aim_url.rstrip("/")
    posts_data = _fetch_json(f"{aim_url}/api/posts?limit=50")
    dir_data   = _fetch_json(f"{aim_url}/api/directory")

    # 3. Build a live-feed page
    posts_html  = ""
    dir_html    = ""
    live_notice = ""

    if posts_data:
        posts = posts_data.get("posts", [])
        posts_html  = _render_posts_fragment(posts)
        live_notice = f"<p class='muted'>Snapshot of {len(posts)} post(s) from the AIM mesh.</p>"
    else:
        posts_html  = "<p class='muted'>AIM bridge not reachable — no live posts in this snapshot.</p>"
        live_notice = ""

    if dir_data:
        entries  = dir_data.get("entries", [])
        dir_html = _render_directory_fragment(entries)
    else:
        dir_html = "<p class='muted'>AIM bridge not reachable — no directory entries in this snapshot.</p>"

    body = (
        f"<h2>Community Posts</h2>\n{live_notice}\n{posts_html}\n"
        f"<h2>AIM Directory</h2>\n{dir_html}\n"
    )
    feed_page = _WWW_WRAPPER.format(title="AIM Live Feed", body=body)
    (dest / "aim-live.html").write_text(feed_page, encoding="utf-8")
    logger.info("Wrote aim-live.html")

    # 4. Write a root index.html that frames the AIM site or links to pages
    def _page_label(filename: str) -> str:
        return filename.replace(".html", "").replace("-", " ").title()

    nav_links = "\n".join(
        f'      <li><a href="{f}">{_page_label(f)}</a></li>'
        for f in sorted(copied)
    )
    index_body = (
        "<h2>AIM Pages</h2>\n"
        f"<ul style='list-style:none;display:flex;flex-wrap:wrap;gap:10px;'>\n{nav_links}\n      </ul>\n"
        "<h2>Live Feed Snapshot</h2>\n"
        "<p><a href='aim-live.html' style='color:var(--accent)'>View community posts and directory →</a></p>\n"
    )
    index_page = _WWW_WRAPPER.format(title="A.I.M. Home", body=index_body)
    (dest / "index.html").write_text(index_page, encoding="utf-8")
    logger.info("Wrote index.html")

    print(f"\n{'='*60}")
    print(f"  AIM → WWW Static Snapshot")
    print(f"  Output directory : {dest.resolve()}")
    print(f"  Static pages     : {len(copied)}")
    print(f"  Live data        : {'yes' if posts_data else 'no (AIM bridge unreachable)'}")
    print(f"  Files written    : index.html, aim-live.html + {len(copied)} AIM pages")
    print(f"{'='*60}")
    print(f"\n  Deploy the '{dest}' folder to any web host (GitHub Pages,")
    print(f"  nginx, Apache, etc.) for traditional WWW access.\n")


# ---------------------------------------------------------------------------
# Directory registration helper
# ---------------------------------------------------------------------------

def register_with_www(
    aim_url: str,
    site_name: str,
    site_url: str,
    description: str = "",
    category: str = "website",
    creator: str = "anonymous",
) -> dict[str, Any] | None:
    """
    Register *site_url* with the AIM directory so it appears in both the
    AIM mesh and the traditional web snapshot.

    Returns the entry dict on success, or None if the AIM bridge is
    unreachable.
    """
    aim_url = aim_url.rstrip("/")
    payload = {
        "name":        site_name,
        "url":         site_url,
        "description": description,
        "category":    category,
        "creator":     creator,
    }
    result = _post_json(f"{aim_url}/api/directory", payload)
    if result:
        logger.info("Registered '%s' (%s) with AIM directory", site_name, site_url)
    else:
        logger.warning("Could not register '%s' — AIM bridge unreachable at %s", site_name, aim_url)
    return result
