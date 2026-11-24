#!/usr/bin/env python3
"""GitHub Release Tracker (Portable Single-File PyQt6 Edition).

A self-contained, portable single-file Python + PyQt6 desktop application that
tracks the latest release of GitHub projects, Forgejo/Gitea repositories
(e.g. https://git.magicbean.dev/MagicBeanDev/Longshot), and project download pages
(e.g. https://eden-emu.dev/downloads/) with:
- A free-text Title column at the very left (Column 0)
- Configurable Source column (PC, Android, Switch, Switch 2, PS5, PS4, PS3, Xbox, Wii, Wii U)
- Configurable Target column (PC, Android, Switch, Switch 2, PS5, PS4, PS3)
- A free-text Comment column at the far right (Column 9)
- Row removal with confirmation (toolbar Remove button, right-click menu, Delete key)
- Persistent column widths saved automatically on resize and on application exit.

Portable runtime behavior:
- Stores `projects.json` (and atomic temp/backup files) directly next to
  `github_release_tracker.py` (or `GitHubReleaseTracker.exe` when frozen) in its
  own directory.
- Automatically generates `icon.ico` next to `github_release_tracker.py` if needed.
- Supports `python github_release_tracker.py` (GUI),
  `python github_release_tracker.py --test` (built-in unit test suite), and
  `python github_release_tracker.py --build-exe` (portable PyInstaller EXE builder).
"""

from __future__ import annotations

import datetime
import html
import json
import os
import re
import struct
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

APP_NAME = "GitHub Release Tracker"
APP_VERSION = "2.0.0"
REPO_URL = "https://github.com/santosasarno-code/github-release-tracker-rs"
NO_DESCRIPTION = "No description, website, or topics provided."
MAX_PROJECTS = 500
MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_CUSTOM_NAME = 80
MAX_COMMENT_LEN = 300
MAX_TITLE_LEN = 300

SOURCE_PLATFORMS: Tuple[str, ...] = (
    "PC",
    "Android",
    "Switch",
    "Switch 2",
    "PS5",
    "PS4",
    "PS3",
    "Xbox",
    "Wii",
    "Wii U",
)

TARGET_PLATFORMS: Tuple[str, ...] = (
    "PC",
    "Android",
    "Switch",
    "Switch 2",
    "PS5",
    "PS4",
    "PS3",
)

PLATFORMS: Tuple[str, ...] = SOURCE_PLATFORMS

SORTABLE: Tuple[str, ...] = (
    "user_title",
    "name",
    "repo",
    "source",
    "target",
    "published",
    "status",
    "comment",
)

COLS: Tuple[Tuple[str, str], ...] = (
    ("user_title", "Title"),
    ("name", "Project"),
    ("repo", "Repository"),
    ("source", "Source"),
    ("target", "Target"),
    ("release", "Current release"),
    ("published", "Published"),
    ("status", "Status"),
    ("checked", "Last checked"),
    ("comment", "Comment"),
)

COL_BASE: Tuple[int, ...] = (150, 180, 210, 105, 105, 135, 110, 210, 125, 180)
COL_MIN: Tuple[int, ...] = (90, 110, 110, 85, 85, 90, 100, 120, 100, 90)
DEFAULT_COL_ORDER: Tuple[str, ...] = tuple(cid for cid, _ in COLS)


# ===========================================================================
# Portable Directory & Self-Generated Assets
# ===========================================================================
def app_dir() -> Path:
    """Return the directory containing this .py script (or frozen .exe)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def data_file_path() -> Path:
    """Store projects.json next to github_release_tracker.py in its own directory."""
    base = app_dir()
    probe = base / f".write_test_{os.getpid()}"
    try:
        probe.write_bytes(b"x")
        probe.unlink(missing_ok=True)
        return base / "projects.json"
    except Exception:
        pass

    appdata = os.environ.get("APPDATA")
    if appdata:
        fallback = Path(appdata) / "GitHubReleaseTracker"
        try:
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback / "projects.json"
        except Exception:
            pass
    return base / "projects.json"


def _make_png_icon_bytes(size: int = 32) -> bytes:
    """Generate a clean 32x32 RGBA PNG icon in pure Python (no external libraries)."""
    raw_rows = bytearray()
    for y in range(size):
        raw_rows.append(0)  # filter type 0
        for x in range(size):
            dx = min(x, size - 1 - x)
            dy = min(y, size - 1 - y)
            if dx + dy < 4 and (dx < 2 or dy < 2):
                raw_rows.extend((0, 0, 0, 0))
                continue
            cx, cy = x - size / 2.0, y - size / 2.0
            in_arrow_shaft = (-3 <= cx <= 3) and (-5 <= cy <= 7)
            in_arrow_head = (cy < -1) and (abs(cx) <= (cy + 9) * 1.15) and (cy >= -9)
            if in_arrow_shaft or in_arrow_head:
                raw_rows.extend((255, 255, 255, 255))
            else:
                raw_rows.extend((47, 111, 191, 255))

    def png_chunk(tag: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(raw_rows), 9)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", idat)
        + png_chunk(b"IEND", b"")
    )


def ensure_portable_icon() -> Optional[Path]:
    """Ensure icon.ico exists next to github_release_tracker.py if needed."""
    ico_path = app_dir() / "icon.ico"
    if ico_path.exists():
        return ico_path
    try:
        png = _make_png_icon_bytes(32)
        ico_header = struct.pack("<HHH", 0, 1, 1)
        ico_entry = struct.pack("<BBBBHHII", 32, 32, 0, 0, 1, 32, len(png), 22)
        ico_path.write_bytes(ico_header + ico_entry + png)
        return ico_path
    except Exception:
        return None


# ===========================================================================
# Core Domain Logic (Platform Validation, Repo/Site Parsing, Feeds & APIs)
# ===========================================================================
class GitHubError(Exception):
    def __init__(self, message: str, kind: str = "other") -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind  # "not_found" | "rate_limit" | "other"

    @classmethod
    def not_found(cls) -> "GitHubError":
        return cls("Not found (wrong name, or a private repository).", kind="not_found")


def default_platform() -> str:
    return "PC"


def normalize_source_platform(value: Any) -> str:
    if isinstance(value, str):
        trimmed = value.strip().lower()
        for p in SOURCE_PLATFORMS:
            if p.lower() == trimmed:
                return p
    return default_platform()


def normalize_target_platform(value: Any) -> str:
    if isinstance(value, str):
        trimmed = value.strip().lower()
        for p in TARGET_PLATFORMS:
            if p.lower() == trimmed:
                return p
    return default_platform()


def normalize_platform(value: Any, is_source: bool = True) -> str:
    if is_source:
        return normalize_source_platform(value)
    return normalize_target_platform(value)


def normalize_col_widths(raw: Any) -> List[int]:
    """Validate and clamp saved column widths to COL_MIN.

    Also migrates 8-column or 9-column saved arrays to the 10-column layout
    (Title at index 0, Comment at index 9).
    """
    if isinstance(raw, (list, tuple)):
        items = list(raw)
        if len(items) == 8:
            items = [COL_BASE[0]] + items + [COL_BASE[-1]]
        elif len(items) == 9:
            items = [COL_BASE[0]] + items
        if len(items) == len(COLS):
            out: List[int] = []
            for i, val in enumerate(items):
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    out.append(max(COL_MIN[i], min(1600, int(val))))
                else:
                    return list(COL_BASE)
            return out
    return list(COL_BASE)


def normalize_col_order(raw: Any) -> List[str]:
    """Validate and normalize saved column order so all column IDs in COLS appear once."""
    valid_ids = [cid for cid, _ in COLS]
    valid_set = set(valid_ids)
    out: List[str] = []
    if isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, str) and item in valid_set and item not in out:
                out.append(item)
    for cid in valid_ids:
        if cid not in out:
            out.append(cid)
    return out


_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def valid_name(s: str) -> bool:
    return bool(isinstance(s, str) and _NAME_RE.match(s))


def _take_name(s: str) -> Tuple[str, str]:
    i = 0
    n = len(s)
    while i < n and (s[i].isalnum() or s[i] in "_.-"):
        i += 1
    return s[:i], s[i:]


def parse_project_input(text: str) -> Optional[Dict[str, str]]:
    """Parse a GitHub URL, owner/repo, Forgejo/Gitea URL, or project download page URL.

    Supported formats:
    1. GitHub shorthand or URL: `owner/repo` or `https://github.com/owner/repo`
    2. Self-hosted Forgejo/Gitea/GitLab/Codeberg URL:
       `https://git.magicbean.dev/MagicBeanDev/Longshot`
    3. Project downloads / website URL:
       `https://eden-emu.dev/downloads/`
    """
    if not isinstance(text, str):
        return None
    trimmed = text.strip()
    if not trimmed:
        return None

    has_scheme = trimmed.startswith("https://") or trimmed.startswith("http://")
    rest = trimmed
    scheme = "https"
    if rest.startswith("https://"):
        rest = rest[8:]
        scheme = "https"
    elif rest.startswith("http://"):
        rest = rest[7:]
        scheme = "http"
    if rest.startswith("www."):
        rest = rest[4:]

    # Case 1: github.com/<owner>/<repo>[/...]
    if rest.startswith("github.com/"):
        after = rest[len("github.com/") :]
        owner, r1 = _take_name(after)
        if owner and r1.startswith("/"):
            repo, _ = _take_name(r1[1:])
            if repo.endswith(".git"):
                repo = repo[:-4]
            if repo and valid_name(owner) and valid_name(repo):
                return {
                    "kind": "github",
                    "host": "github.com",
                    "owner": owner,
                    "repo": repo,
                    "html_url": f"https://github.com/{owner}/{repo}",
                }
        return None

    # Case 2: Full HTTP(S) URL to another host (e.g. git.magicbean.dev or eden-emu.dev)
    if has_scheme:
        parts = rest.split("/")
        host = parts[0].strip().lower()
        if not host or "." not in host or not valid_name(host):
            return None
        segs = [s for s in parts[1:] if s]
        # Strip query/fragment from last segment
        if segs:
            segs[-1] = re.split(r"[?#]", segs[-1])[0]
            segs = [s for s in segs if s]

        # 2a: Two or more path segments where first two are valid owner/repo names
        # e.g. https://git.magicbean.dev/MagicBeanDev/Longshot
        if len(segs) >= 2 and valid_name(segs[0]) and valid_name(segs[1]):
            owner = segs[0]
            repo = segs[1][:-4] if segs[1].endswith(".git") else segs[1]
            if repo and valid_name(repo):
                return {
                    "kind": "forge",
                    "host": host,
                    "owner": owner,
                    "repo": repo,
                    "html_url": f"{scheme}://{host}/{owner}/{repo}",
                }

        # 2b: Single-segment or downloads/project webpage URL
        # e.g. https://eden-emu.dev/downloads/ or https://eden-emu.dev
        slug = segs[0] if segs and valid_name(segs[0]) else host.split(".")[0]
        if not valid_name(slug):
            slug = "releases"
        clean_path = "/".join(segs)
        trailing = "/" if trimmed.endswith("/") and clean_path else ""
        full_url = (
            f"{scheme}://{host}/{clean_path}{trailing}"
            if clean_path
            else f"{scheme}://{host}"
        )
        return {
            "kind": "web",
            "host": host,
            "owner": host,
            "repo": slug,
            "html_url": full_url,
        }

    # Case 3: Plain owner/repo shorthand (no scheme)
    owner, r1 = _take_name(trimmed)
    if not r1.startswith("/"):
        return None
    repo, tail = _take_name(r1[1:])
    if not owner or not repo or tail:
        return None
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not repo or not valid_name(owner) or not valid_name(repo):
        return None
    return {
        "kind": "github",
        "host": "github.com",
        "owner": owner,
        "repo": repo,
        "html_url": f"https://github.com/{owner}/{repo}",
    }


def parse_repo(text: str) -> Optional[Tuple[str, str]]:
    """Accept GitHub URLs, owner/repo, Forgejo/Gitea URLs, or download site URLs."""
    info = parse_project_input(text)
    if not info:
        return None
    return info["owner"], info["repo"]


def _str_field(v: Any, limit: int) -> str:
    if isinstance(v, str):
        return v.strip()[:limit]
    return ""


def safe_http_url(url: Any, fallback: str) -> str:
    if (
        isinstance(url, str)
        and (url.startswith("https://") or url.startswith("http://"))
        and len(url) < 500
        and not any(c.isspace() for c in url)
    ):
        return url
    return fallback


def safe_github_url(url: Any, fallback: str) -> str:
    return safe_http_url(url, fallback)


def _id_value(v: Any) -> Optional[Union[int, str]]:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        return v[:300]
    return None


def clean_name(s: str) -> str:
    if not isinstance(s, str):
        return ""
    joined = " ".join(s.split())
    return joined[:MAX_CUSTOM_NAME].strip()


def clean_comment(s: Any) -> str:
    if not isinstance(s, str):
        return ""
    return s.replace("\r", " ").replace("\n", " ").strip()[:MAX_COMMENT_LEN]


def clean_user_title(s: Any) -> str:
    if not isinstance(s, str):
        return ""
    return s.replace("\r", " ").replace("\n", " ").strip()[:MAX_TITLE_LEN]


def now_iso() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def today_ymd() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")


def project_key(p: Dict[str, Any]) -> str:
    html_url = str(p.get("html_url") or "").strip().lower()
    if (
        html_url
        and not html_url.startswith("https://github.com/")
        and not html_url.startswith("http://github.com/")
    ):
        cleaned = re.sub(r"^https?://(?:www\.)?", "", html_url).rstrip("/")
        if cleaned:
            return cleaned
    return f"{p.get('owner', '')}/{p.get('repo', '')}".lower()


def repo_display_label(p: Dict[str, Any]) -> str:
    """Return 'owner/repo' for GitHub projects or 'host/path' for external sites."""
    html_url = str(p.get("html_url") or "").strip()
    if (
        html_url
        and not html_url.startswith("https://github.com/")
        and not html_url.startswith("http://github.com/")
    ):
        cleaned = re.sub(r"^https?://(?:www\.)?", "", html_url).rstrip("/")
        if cleaned:
            return cleaned
    return f"{p.get('owner', '')}/{p.get('repo', '')}"


def display_name(p: Dict[str, Any]) -> str:
    custom = p.get("custom_name")
    if isinstance(custom, str) and custom:
        return custom
    title = p.get("title", "")
    return title if title else p.get("repo", "")


def has_update(p: Dict[str, Any]) -> bool:
    latest = p.get("latest")
    if not isinstance(latest, dict):
        return False
    return latest.get("id") != p.get("seen_id")


def status_text(p: Dict[str, Any]) -> str:
    err = p.get("error")
    if isinstance(err, str) and err:
        return f"Error: {err}"
    latest = p.get("latest")
    if not isinstance(latest, dict):
        return "No releases published"
    if has_update(p):
        new_lbl = latest.get("tag") or latest.get("name") or "new release"
        old_tag = p.get("seen_tag")
        if isinstance(old_tag, str) and old_tag:
            return f"Update available: {old_tag} -> {new_lbl}"
        return f"Update available: {new_lbl}"
    return "Up to date"


def status_rank(p: Dict[str, Any]) -> int:
    if p.get("error"):
        return 1
    if not isinstance(p.get("latest"), dict):
        return 2
    if has_update(p):
        return 0
    return 3


def release_label(p: Dict[str, Any]) -> str:
    latest = p.get("latest")
    if not isinstance(latest, dict):
        return "-"
    s = latest.get("tag") or latest.get("name") or ""
    if latest.get("source") == "tag":
        s += " (tag)"
    elif latest.get("prerelease"):
        s += " (pre-release)"
    return s if s else "-"


def published_label(p: Dict[str, Any]) -> str:
    latest = p.get("latest")
    if not isinstance(latest, dict):
        return "-"
    d = str(latest.get("published_at", ""))[:10]
    return d if d else "-"


def checked_label(p: Dict[str, Any]) -> str:
    s = str(p.get("last_checked", ""))[:16].replace("T", " ")
    return s if s else "never"


def apply_result(
    p: Dict[str, Any],
    latest: Optional[Dict[str, Any]],
    err: Optional[str],
    now: str,
) -> None:
    p["last_checked"] = now
    if err:
        p["error"] = err
        return
    p["error"] = None
    if isinstance(latest, dict):
        seen_tag = p.get("seen_tag")
        if isinstance(seen_tag, str) and seen_tag and seen_tag == latest.get("tag"):
            p["seen_id"] = latest.get("id")
        elif p.get("fmt") != 2 and p.get("seen_id") is None:
            p["seen_id"] = latest.get("id")
            p["seen_tag"] = latest.get("tag")
    p["latest"] = latest
    p["fmt"] = 2


def apply_rename(p: Dict[str, Any], typed: str) -> Optional[str]:
    text = clean_name(typed)
    original = p.get("title") or p.get("repo", "")
    before = display_name(p)
    if text and text != original:
        p["custom_name"] = text
    else:
        p.pop("custom_name", None)
    after = display_name(p)
    if after == before:
        return None
    if "custom_name" in p:
        return f"Renamed to {after}."
    return f"Name reset to {after}."


def apply_user_title(p: Dict[str, Any], typed: str) -> Optional[str]:
    text = clean_user_title(typed)
    before = clean_user_title(p.get("user_title", ""))
    if text == before:
        return None
    p["user_title"] = text
    return (
        f"Title set to '{text}' for {display_name(p)}."
        if text
        else f"Title cleared for {display_name(p)}."
    )


def apply_comment(p: Dict[str, Any], typed: str) -> Optional[str]:
    text = clean_comment(typed)
    before = clean_comment(p.get("comment", ""))
    if text == before:
        return None
    p["comment"] = text
    return (
        f"Comment updated for {display_name(p)}."
        if text
        else f"Comment cleared for {display_name(p)}."
    )


def _normalize_release(
    v: Any, owner: str, repo: str, base_html_url: str = ""
) -> Optional[Dict[str, Any]]:
    if not isinstance(v, dict):
        return None
    tag = _str_field(v.get("tag"), 200)
    rid = _id_value(v.get("id"))
    if rid is None:
        if tag:
            rid = tag
        else:
            return None
    src = v.get("source")
    if src not in ("release", "tag", "feed"):
        src = "release"
    fallback_url = (
        f"{base_html_url.rstrip('/')}/releases"
        if base_html_url
        else f"https://github.com/{owner}/{repo}/releases"
    )
    return {
        "id": rid,
        "tag": tag,
        "name": _str_field(v.get("name"), 300),
        "published_at": _str_field(v.get("published_at"), 40),
        "url": safe_http_url(v.get("url"), fallback_url),
        "prerelease": bool(v.get("prerelease", False)),
        "source": src,
    }


def normalize_project(raw: Any) -> Optional[Dict[str, Any]]:
    if isinstance(raw, str):
        parsed = parse_project_input(raw)
        if not parsed:
            return None
        o: Dict[str, Any] = {
            "owner": parsed["owner"],
            "repo": parsed["repo"],
            "html_url": parsed["html_url"],
        }
    elif isinstance(raw, dict):
        o = raw
    else:
        return None

    owner = o.get("owner")
    repo = o.get("repo")
    if not isinstance(owner, str) or not isinstance(repo, str):
        return None
    if not valid_name(owner) or not valid_name(repo):
        return None

    title = _str_field(o.get("title"), 200)
    custom = clean_name(o["custom_name"]) if isinstance(o.get("custom_name"), str) else ""
    error = _str_field(o.get("error"), 300)
    seen_tag = _str_field(o.get("seen_tag"), 200)
    comment = clean_comment(o.get("comment", ""))
    user_title = clean_user_title(o.get("user_title", ""))
    html_url = safe_http_url(o.get("html_url"), f"https://github.com/{owner}/{repo}")

    proj: Dict[str, Any] = {
        "owner": owner,
        "repo": repo,
        "title": title if title else repo,
        "user_title": user_title,
        "description": _str_field(o.get("description"), 500),
        "html_url": html_url,
        "include_prereleases": bool(o.get("include_prereleases", True)),
        "fmt": 2 if o.get("fmt") == 2 else None,
        "latest": _normalize_release(o.get("latest"), owner, repo, html_url),
        "seen_id": _id_value(o.get("seen_id")),
        "seen_tag": seen_tag if seen_tag else None,
        "last_checked": _str_field(o.get("last_checked"), 40),
        "error": error if error else None,
        "comment": comment,
        "source": normalize_source_platform(o.get("source")),
        "target": normalize_target_platform(o.get("target")),
    }
    if custom:
        proj["custom_name"] = custom
    return proj


def parse_import(raw: Any) -> Optional[Tuple[List[Dict[str, Any]], int]]:
    if isinstance(raw, dict):
        items = raw.get("projects")
        if not isinstance(items, list):
            return None
    elif isinstance(raw, list):
        items = raw
    else:
        return None

    seen = set()
    out: List[Dict[str, Any]] = []
    skipped = max(0, len(items) - MAX_PROJECTS)
    for item in items[:MAX_PROJECTS]:
        p = normalize_project(item)
        if p is not None:
            k = project_key(p)
            if k not in seen:
                seen.add(k)
                out.append(p)
                continue
        skipped += 1
    return out, skipped


def merge_projects(
    existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]
) -> int:
    keys = {project_key(p) for p in existing}
    added = 0
    for p in incoming:
        k = project_key(p)
        if k not in keys:
            keys.add(k)
            existing.append(p)
            added += 1
    return added


def build_export(projects: List[Dict[str, Any]], now: str) -> Dict[str, Any]:
    return {
        "app": APP_NAME,
        "format": 2,
        "exported_at": now,
        "projects": projects,
    }


def default_data() -> Dict[str, Any]:
    return {
        "settings": {
            "token": "",
            "check_on_launch": False,
            "theme": "",
            "sort_col": "",
            "sort_asc": True,
            "col_widths": list(COL_BASE),
            "col_order": list(DEFAULT_COL_ORDER),
        },
        "projects": [],
    }


def parse_data(text: str) -> Optional[Dict[str, Any]]:
    if not isinstance(text, str):
        return None
    text = text.lstrip("\ufeff")
    try:
        v = json.loads(text)
    except Exception:
        return None
    if not isinstance(v, dict):
        return None
    if "projects" in v and not isinstance(v["projects"], list):
        return None

    data = default_data()
    s = v.get("settings")
    if isinstance(s, dict):
        data["settings"]["token"] = _str_field(s.get("token"), 200)
        data["settings"]["check_on_launch"] = bool(s.get("check_on_launch", False))
        theme = s.get("theme")
        data["settings"]["theme"] = theme if theme in ("light", "dark") else ""
        sc = s.get("sort_col")
        data["settings"]["sort_col"] = sc if sc in SORTABLE else ""
        data["settings"]["sort_asc"] = s.get("sort_asc") is not False
        data["settings"]["col_widths"] = normalize_col_widths(s.get("col_widths"))
        data["settings"]["col_order"] = normalize_col_order(s.get("col_order"))

    parsed = parse_import(v)
    data["projects"] = parsed[0] if parsed else []
    return data


def data_to_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def load_data(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return default_data()
    try:
        text = path.read_text(encoding="utf-8")
        parsed = parse_data(text)
        if parsed is not None:
            return parsed
    except Exception:
        pass
    try:
        bak = path.with_suffix(path.suffix + ".bak")
        path.replace(bak)
    except Exception:
        pass
    return default_data()


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def sort_order(projects: List[Dict[str, Any]], col: str, asc: bool) -> List[int]:
    idx = list(range(len(projects)))

    def title_key(p: Dict[str, Any]) -> str:
        return display_name(p).lower()

    def pub_key(p: Dict[str, Any]) -> str:
        latest = p.get("latest")
        return str(latest.get("published_at", "")) if isinstance(latest, dict) else ""

    if col == "status":
        sign = 1 if asc else -1
        idx.sort(
            key=lambda i: (
                sign * status_rank(projects[i]),
                title_key(projects[i]),
                project_key(projects[i]),
            )
        )
    elif col == "user_title":
        idx.sort(
            key=lambda i: (
                str(projects[i].get("user_title", "")).lower(),
                title_key(projects[i]),
                project_key(projects[i]),
            ),
            reverse=not asc,
        )
    elif col == "comment":
        idx.sort(
            key=lambda i: (
                str(projects[i].get("comment", "")).lower(),
                title_key(projects[i]),
                project_key(projects[i]),
            ),
            reverse=not asc,
        )
    elif col == "name":
        idx.sort(
            key=lambda i: (title_key(projects[i]), project_key(projects[i])),
            reverse=not asc,
        )
    elif col == "repo":
        idx.sort(key=lambda i: repo_display_label(projects[i]).lower(), reverse=not asc)
    elif col == "source":
        idx.sort(
            key=lambda i: (
                str(projects[i].get("source", "PC")).lower(),
                title_key(projects[i]),
                project_key(projects[i]),
            ),
            reverse=not asc,
        )
    elif col == "target":
        idx.sort(
            key=lambda i: (
                str(projects[i].get("target", "PC")).lower(),
                title_key(projects[i]),
                project_key(projects[i]),
            ),
            reverse=not asc,
        )
    elif col == "published":
        dated = [i for i in idx if pub_key(projects[i])]
        undated = [i for i in idx if not pub_key(projects[i])]
        dated.sort(
            key=lambda i: (pub_key(projects[i]), title_key(projects[i])),
            reverse=not asc,
        )
        undated.sort(key=lambda i: title_key(projects[i]))
        idx = dated + undated
    else:
        idx.sort(key=lambda i: (not has_update(projects[i]), title_key(projects[i])))
    return idx


def project_column_texts(p: Dict[str, Any]) -> List[str]:
    """Return the visible text values of all 10 table columns for a project row."""
    return [
        str(p.get("user_title", "")),
        display_name(p),
        repo_display_label(p),
        str(p.get("source", "PC")),
        str(p.get("target", "PC")),
        release_label(p),
        published_label(p),
        status_text(p),
        checked_label(p),
        str(p.get("comment", "")),
    ]


def project_matches_search(p: Dict[str, Any], query: str) -> bool:
    """Return True if all keyword tokens in query match across any of the 10 columns of project p."""
    if not isinstance(query, str):
        return True
    q = query.strip().lower()
    if not q:
        return True
    latest = p.get("latest") if isinstance(p.get("latest"), dict) else {}
    parts = project_column_texts(p) + [
        str(p.get("title", "")),
        str(p.get("custom_name", "")),
        f"{p.get('owner', '')}/{p.get('repo', '')}",
        str(p.get("html_url", "")),
        str(latest.get("tag", "")) if isinstance(latest, dict) else "",
        str(latest.get("name", "")) if isinstance(latest, dict) else "",
    ]
    haystack = "\n".join(parts).lower()
    tokens = [tok for tok in q.split() if tok]
    return all(tok in haystack for tok in tokens)


def filter_indices(
    projects: List[Dict[str, Any]], indices: List[int], query: str
) -> List[int]:
    """Filter sorted project indices by a search query across all columns."""
    if not isinstance(query, str) or not query.strip():
        return list(indices)
    return [
        ix
        for ix in indices
        if 0 <= ix < len(projects) and project_matches_search(projects[ix], query)
    ]


def layout_columns(base: Tuple[int, ...], low: Tuple[int, ...], avail: int) -> List[int]:
    total_pref = sum(base)
    total_low = sum(low)
    if avail >= total_pref:
        target = [p * avail / total_pref for p in base]
    else:
        t = max(0.0, (avail - total_low) / max(1, total_pref - total_low))
        target = [lo + (p - lo) * t for p, lo in zip(base, low)]
    sizes = [max(lo, int(x)) for x, lo in zip(target, low)]
    status_idx = 7 if len(sizes) > 7 else (len(sizes) - 2)
    if avail >= total_low and len(sizes) > status_idx:
        sizes[status_idx] += max(0, avail - sum(sizes))
    return sizes


def parse_feed(
    body: str, owner: str, repo: str, base_url: str = ""
) -> Optional[Dict[str, Any]]:
    """Parse an Atom release feed from GitHub, Forgejo, Gitea, Codeberg, or GitLab."""
    if not re.search(r"<feed[\s>/]", body):
        raise GitHubError("Release feed was not valid XML.")
    m = re.search(r"<entry[\s>][\s\S]*?</entry>", body)
    if not m:
        return None
    entry = m.group(0)

    def elem_text(name: str) -> str:
        em = re.search(rf"<{name}(?:\s[^>]*)?>([\s\S]*?)</{name}>", entry)
        return html.unescape(em.group(1).strip()) if em else ""

    entry_id = elem_text("id")
    title = elem_text("title")
    updated = elem_text("updated") or elem_text("published")

    href = ""
    for lm in re.finditer(r"<link\s+([^>]+?)/?>", entry):
        attrs = lm.group(1)
        rel_m = re.search(r"""\brel\s*=\s*["']([^"']*)["']""", attrs)
        rel = rel_m.group(1) if rel_m else "alternate"
        if rel == "alternate":
            href_m = re.search(r"""\bhref\s*=\s*["']([^"']*)["']""", attrs)
            if href_m:
                href = html.unescape(href_m.group(1))
                break

    # Forgejo / Gitea feeds put the release URL inside <id>, e.g.:
    # <id>12210: https://git.magicbean.dev/MagicBeanDev/Longshot/releases/tag/v3.1.1</id>
    if not href and ("https://" in entry_id or "http://" in entry_id):
        url_m = re.search(r"https?://[^\s<>\"']+", entry_id)
        if url_m:
            href = url_m.group(0)

    marker = "/releases/tag/"
    tag = ""
    if marker in href:
        tag = urllib.parse.unquote(href.split(marker, 1)[1])
    elif marker in entry_id:
        tag = urllib.parse.unquote(entry_id.split(marker, 1)[1])
    elif "Repository/" in entry_id:
        r = entry_id.split("Repository/", 1)[1]
        if "/" in r:
            prefix, rest_tag = r.split("/", 1)
            if prefix.isdigit() and rest_tag:
                tag = rest_tag

    if not tag and title:
        ver_m = re.search(r"\b(v?\d+\.\d+(?:\.\d+)*(?:-[0-9A-Za-z._-]+)?)\b", title)
        if ver_m:
            tag = ver_m.group(1)

    if not entry_id and not tag:
        return None

    fallback_url = (
        f"{base_url.rstrip('/')}/releases"
        if base_url
        else f"https://github.com/{owner}/{repo}/releases"
    )
    return {
        "id": entry_id if entry_id else tag,
        "tag": tag,
        "name": title,
        "published_at": updated,
        "url": href if href else fallback_url,
        "prerelease": False,
        "source": "feed",
    }


def extract_releases_from_webpage(
    html_body: str, page_url: str
) -> Tuple[Optional[Tuple[str, str, str]], Optional[Dict[str, Any]], Dict[str, str]]:
    """Inspect a project downloads webpage (such as https://eden-emu.dev/downloads/).

    Returns:
      (linked_forge_repo, direct_release, page_meta)
      - linked_forge_repo: (base_host_url, owner, repo) if the page links to a
        Forgejo/Gitea/GitHub `/owner/repo/releases` repository (preferring Stable).
      - direct_release: A Release dict if versions are listed directly on the page.
      - page_meta: {'title': ..., 'description': ...} extracted from HTML meta/title tags.
    """
    meta_title = ""
    meta_desc = ""

    site_m = re.search(
        r"""<meta\s+[^>]*property=["']og:site_name["'][^>]*content=["']([^"']+)["']""",
        html_body,
        re.IGNORECASE,
    )
    if site_m:
        meta_title = html.unescape(site_m.group(1).strip())
    if not meta_title:
        title_m = re.search(
            r"<title[^>]*>([\s\S]*?)</title>", html_body, re.IGNORECASE
        )
        if title_m:
            raw_t = html.unescape(title_m.group(1).strip())
            meta_title = raw_t.split(" - ")[0].split(" | ")[0].strip()

    desc_m = re.search(
        r"""<meta\s+[^>]*name=["']description["'][^>]*content=["']([^"']+)["']""",
        html_body,
        re.IGNORECASE,
    )
    if not desc_m:
        desc_m = re.search(
            r"""<meta\s+[^>]*property=["']og:description["'][^>]*content=["']([^"']+)["']""",
            html_body,
            re.IGNORECASE,
        )
    if desc_m:
        meta_desc = html.unescape(desc_m.group(1).strip())

    page_meta = {"title": meta_title, "description": meta_desc}

    # Look for links to a GitHub/Forgejo/Gitea releases page:
    # e.g. https://git.eden-emu.dev/eden-emu/eden/releases
    candidates: List[Tuple[int, str, str, str]] = []
    for m in re.finditer(
        r"""href\s*=\s*["'](https?://([^/"'\s<>]+)/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/releases(?:/tag/[^"'\s<>?#]+)?)["']""",
        html_body,
        re.IGNORECASE,
    ):
        full_href, host, owner, repo = m.group(1), m.group(2), m.group(3), m.group(4)
        # Prefer non-nightly / stable links first
        is_nightly = (
            "nightly" in owner.lower()
            or "nightly" in repo.lower()
            or "nightly" in full_href.lower()
        )
        prio = 1 if is_nightly else 0
        scheme = "https" if full_href.startswith("https://") else "http"
        candidates.append((prio, f"{scheme}://{host}", owner, repo))

    if candidates:
        candidates.sort(key=lambda x: x[0])
        _, base_host, owner, repo = candidates[0]
        return (base_host, owner, repo), None, page_meta

    # Fallback: scan page for direct versioned download links or release headings
    ver_m = re.search(
        r"\b(v\d+\.\d+(?:\.\d+)*(?:-[0-9A-Za-z._-]+)?)\b",
        html_body,
        re.IGNORECASE,
    )
    if ver_m:
        tag = ver_m.group(1)
        date_m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", html_body)
        pub_date = date_m.group(1) if date_m else ""
        return (
            None,
            {
                "id": f"{page_url}#{tag}",
                "tag": tag,
                "name": f"{meta_title or 'Release'} {tag}".strip(),
                "published_at": pub_date,
                "url": page_url,
                "prerelease": False,
                "source": "feed",
            },
            page_meta,
        )

    return None, None, page_meta


class HttpNet:
    """Standard-library HTTP(S) client for GitHub, Forgejo/Gitea, and download pages."""

    def __init__(self) -> None:
        self.rate_remaining: Optional[int] = None

    def url_get(
        self, url: str, accept: str = "*/*", token: str = ""
    ) -> Tuple[str, Dict[str, str]]:
        headers = {
            "User-Agent": "GitHubReleaseTracker/2.0",
            "Accept": accept,
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                hdrs = {k.lower(): v for k, v in resp.headers.items()}
                body = resp.read().decode("utf-8", errors="replace")
                return body, hdrs
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise GitHubError.not_found()
            if e.code == 429:
                raise GitHubError(
                    "Server is rate-limiting requests (429). Try again later.",
                    kind="rate_limit",
                )
            raise GitHubError(f"Server returned HTTP {e.code}.")
        except Exception as e:
            raise GitHubError(f"Network error: {e}")

    def api_get(self, path: str, token: str = "") -> Any:
        url = (
            path
            if path.startswith("https://") or path.startswith("http://")
            else f"https://api.github.com{path}"
        )
        headers = {
            "Accept": "application/vnd.github+json, application/json",
            "User-Agent": "GitHubReleaseTracker",
        }
        if url.startswith("https://api.github.com"):
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                rem = resp.headers.get("X-RateLimit-Remaining")
                if rem is not None and rem.strip().isdigit():
                    self.rate_remaining = int(rem.strip())
                body = resp.read().decode("utf-8", errors="replace")
                return json.loads(body)
        except urllib.error.HTTPError as e:
            rem = e.headers.get("X-RateLimit-Remaining") if e.headers else None
            reset = e.headers.get("X-RateLimit-Reset") if e.headers else None
            if rem is not None and rem.strip().isdigit():
                self.rate_remaining = int(rem.strip())
            if e.code in (403, 429) and rem and rem.strip() == "0":
                self.rate_remaining = 0
                when = ""
                if reset and reset.strip().isdigit():
                    dt = datetime.datetime.fromtimestamp(int(reset.strip()))
                    when = f" Resets at {dt.strftime('%H:%M')}."
                raise GitHubError(
                    f"GitHub API rate limit reached.{when} Add a token in Settings for a higher limit.",
                    kind="rate_limit",
                )
            if e.code == 404:
                raise GitHubError.not_found()
            if e.code == 401:
                raise GitHubError("GitHub rejected the token (401). Check it in Settings.")
            raise GitHubError(f"GitHub returned HTTP {e.code}.")
        except Exception as e:
            raise GitHubError(f"Network error: {e}")

    def feed_get(self, owner: str, repo: str, base_host: str = "https://github.com") -> str:
        url = f"{base_host.rstrip('/')}/{owner}/{repo}/releases.atom"
        body, _ = self.url_get(
            url, accept="application/atom+xml, application/xml;q=0.9, */*;q=0.8"
        )
        return body


def _release_from_api(r: Dict[str, Any]) -> Dict[str, Any]:
    tag = str(r.get("tag_name") or "")
    published = str(r.get("published_at") or r.get("created_at") or "")
    rid = _id_value(r.get("id"))
    return {
        "id": rid if rid is not None else tag,
        "tag": tag,
        "name": str(r.get("name") or ""),
        "published_at": published,
        "url": str(r.get("html_url") or ""),
        "prerelease": bool(r.get("prerelease", False)),
        "source": "release",
    }


def _external_host_info(
    owner: str, repo: str, html_url: str = ""
) -> Tuple[str, str, str, str]:
    """Classify project endpoint: ('github'|'forge'|'web', base_host, owner, repo)."""
    if html_url:
        parsed = parse_project_input(html_url)
        if parsed:
            scheme = "http" if html_url.startswith("http://") else "https"
            return (
                parsed["kind"],
                f"{scheme}://{parsed['host']}",
                parsed["owner"],
                parsed["repo"],
            )
    return ("github", "https://github.com", owner, repo)


def fetch_repo_info(
    net: Any, owner: str, repo: str, token: str = "", html_url: str = ""
) -> Dict[str, str]:
    kind, base_host, ro, rr = _external_host_info(owner, repo, html_url)
    if kind == "github":
        d = net.api_get(f"/repos/{ro}/{rr}", token)
        full = str(d.get("full_name") or f"{ro}/{rr}")
        if "/" in full:
            ro, rr = full.split("/", 1)
        return {
            "owner": ro,
            "repo": rr,
            "title": str(d.get("name") or rr),
            "description": str(d.get("description") or ""),
            "html_url": str(d.get("html_url") or f"https://github.com/{full}"),
        }

    if kind == "forge":
        # Forgejo / Gitea REST API v1: /api/v1/repos/{owner}/{repo}
        try:
            d = net.api_get(f"{base_host}/api/v1/repos/{ro}/{rr}")
            if isinstance(d, dict):
                return {
                    "owner": ro,
                    "repo": rr,
                    "title": str(d.get("name") or rr),
                    "description": str(d.get("description") or ""),
                    "html_url": str(d.get("html_url") or f"{base_host}/{ro}/{rr}"),
                }
        except Exception:
            pass
        return {
            "owner": ro,
            "repo": rr,
            "title": rr,
            "description": "",
            "html_url": html_url or f"{base_host}/{ro}/{rr}",
        }

    # Web / Downloads page (e.g. https://eden-emu.dev/downloads/)
    target_url = html_url or f"{base_host}/{rr}"
    body, _ = net.url_get(target_url, accept="text/html,application/xhtml+xml,*/*")
    linked_forge, _, page_meta = extract_releases_from_webpage(body, target_url)
    title = page_meta.get("title") or rr
    desc = page_meta.get("description") or ""
    if linked_forge:
        f_host, f_owner, f_repo = linked_forge
        try:
            d = net.api_get(f"{f_host}/api/v1/repos/{f_owner}/{f_repo}")
            if isinstance(d, dict):
                if not desc:
                    desc = str(d.get("description") or "")
                if not page_meta.get("title"):
                    title = str(d.get("name") or title)
        except Exception:
            pass
    return {
        "owner": ro,
        "repo": rr,
        "title": title,
        "description": desc,
        "html_url": target_url,
    }


def fetch_latest_release(
    net: Any,
    owner: str,
    repo: str,
    token: str,
    include_pre: bool,
    base_host: str = "https://github.com",
) -> Optional[Dict[str, Any]]:
    is_github = "github.com" in base_host.lower()
    api_prefix = (
        f"/repos/{owner}/{repo}"
        if is_github
        else f"{base_host.rstrip('/')}/api/v1/repos/{owner}/{repo}"
    )
    tok = token if is_github else ""

    if not include_pre:
        try:
            v = net.api_get(f"{api_prefix}/releases/latest", tok)
            if isinstance(v, dict):
                return _release_from_api(v)
        except GitHubError as e:
            if e.kind != "not_found":
                raise

    try:
        q = "per_page=10" if is_github else "limit=10"
        data = net.api_get(f"{api_prefix}/releases?{q}", tok)
        if isinstance(data, list):
            for r in data:
                if isinstance(r, dict) and not r.get("draft"):
                    if not include_pre and r.get("prerelease"):
                        continue
                    return _release_from_api(r)
    except GitHubError as e:
        if e.kind != "not_found":
            raise

    try:
        q = "per_page=1" if is_github else "limit=1"
        tags = net.api_get(f"{api_prefix}/tags?{q}", tok)
        if isinstance(tags, list) and tags:
            t = tags[0]
            name = str(t.get("name") or "")
            commit = t.get("commit") if isinstance(t.get("commit"), dict) else {}
            sha = str(commit.get("sha") or t.get("id") or name)
            pub = str(commit.get("created") or "")
            return {
                "id": sha,
                "url": f"{base_host.rstrip('/')}/{owner}/{repo}/releases/tag/{urllib.parse.quote(name, safe='')}",
                "tag": name,
                "name": str(t.get("message") or "").splitlines()[0] if t.get("message") else "",
                "published_at": pub,
                "prerelease": False,
                "source": "tag",
            }
    except GitHubError as e:
        if e.kind != "not_found":
            raise
    return None


def get_latest(
    net: Any,
    owner: str,
    repo: str,
    token: str = "",
    include_pre: bool = True,
    html_url: str = "",
) -> Optional[Dict[str, Any]]:
    kind, base_host, ro, rr = _external_host_info(owner, repo, html_url)

    if kind == "web":
        target_url = html_url or f"{base_host}/{rr}"
        body, _ = net.url_get(target_url, accept="text/html,application/xhtml+xml,*/*")
        linked_forge, direct_rel, _ = extract_releases_from_webpage(body, target_url)
        if linked_forge:
            f_host, f_owner, f_repo = linked_forge
            if include_pre:
                try:
                    feed_xml = net.feed_get(f_owner, f_repo, f_host)
                    rel = parse_feed(
                        feed_xml, f_owner, f_repo, f"{f_host}/{f_owner}/{f_repo}"
                    )
                    if rel is not None:
                        return rel
                except Exception:
                    pass
            return fetch_latest_release(
                net, f_owner, f_repo, "", include_pre, base_host=f_host
            )
        return direct_rel

    if include_pre:
        try:
            if kind == "github":
                body = net.feed_get(ro, rr)
            else:
                body = net.feed_get(ro, rr, base_host)
            rel = parse_feed(body, ro, rr, f"{base_host}/{ro}/{rr}")
            if rel is not None:
                return rel
        except Exception:
            pass
    return fetch_latest_release(net, ro, rr, token, include_pre, base_host=base_host)


def get_palette(dark: bool) -> Dict[str, str]:
    if dark:
        return {
            "bg": "#202124",
            "fg": "#e8eaed",
            "field": "#2b2d31",
            "sel_bg": "#2f6fbf",
            "sel_fg": "#ffffff",
            "btn_bg": "#3a3d42",
            "btn_active": "#4a4d52",
            "border": "#4a4d52",
            "update_bg": "#4d4210",
            "update_fg": "#ffe9a6",
            "error_fg": "#ff8a80",
            "none_fg": "#9aa0a6",
            "sub_fg": "#9aa0a6",
            "line": "#3d4046",
            "link": "#4da3ff",
            "head_bg": "#33363b",
        }
    return {
        "bg": "#f3f3f3",
        "fg": "#1b1b1b",
        "field": "#ffffff",
        "sel_bg": "#0078d4",
        "sel_fg": "#ffffff",
        "btn_bg": "#e1e1e1",
        "btn_active": "#d0d0d0",
        "border": "#bdbdbd",
        "update_bg": "#fff3cd",
        "update_fg": "#1b1b1b",
        "error_fg": "#b00020",
        "none_fg": "#777777",
        "sub_fg": "#666666",
        "line": "#d4d4d4",
        "link": "#0b57d0",
        "head_bg": "#e5e5e5",
    }


def detect_system_dark() -> bool:
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return int(val) == 0
        except Exception:
            return True
    return True


# ===========================================================================
# PyQt6 Desktop GUI (Loaded when launching the application)
# ===========================================================================
def run_gui() -> int:
    try:
        from PyQt6.QtCore import QEvent, QObject, Qt, QThread, QUrl, pyqtSignal
        from PyQt6.QtGui import (
            QAction,
            QColor,
            QDesktopServices,
            QFont,
            QIcon,
            QKeySequence,
            QShortcut,
        )
        from PyQt6.QtWidgets import (
            QAbstractItemView,
            QApplication,
            QCheckBox,
            QComboBox,
            QDialog,
            QFileDialog,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QListWidget,
            QListWidgetItem,
            QMainWindow,
            QMenu,
            QMessageBox,
            QPushButton,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )
    except ImportError as exc:
        sys.stderr.write(
            f"PyQt6 is required to run the GUI ({exc}).\n"
            "Install it with: pip install PyQt6\n"
            "Or run unit tests with: python github_release_tracker.py --test\n"
        )
        return 1

    class RowSelectFilter(QObject):
        """Ensures clicking a cell widget selects its row in QTableWidget safely."""

        def __init__(self, win: "MainWindow", widget: QWidget, row: int) -> None:
            super().__init__(widget)
            self.win = win
            self.row = row

        def eventFilter(self, obj: QObject, event: QEvent) -> bool:
            if self.win.suppress_events:
                return False
            if event.type() == QEvent.Type.MouseButtonPress:
                table = self.win.table
                if 0 <= self.row < table.rowCount():
                    selected_rows = {idx.row() for idx in table.selectedIndexes()}
                    if self.row not in selected_rows:
                        table.selectRow(self.row)
            return False

    class AddProjectWorker(QThread):
        finished_add = pyqtSignal(object, object)

        def __init__(
            self, net: HttpNet, owner: str, repo: str, html_url: str, token: str
        ) -> None:
            super().__init__()
            self.net = net
            self.owner = owner
            self.repo = repo
            self.html_url = html_url
            self.token = token

        def run(self) -> None:
            try:
                latest = get_latest(
                    self.net,
                    self.owner,
                    self.repo,
                    self.token,
                    True,
                    html_url=self.html_url,
                )
                try:
                    info = fetch_repo_info(
                        self.net,
                        self.owner,
                        self.repo,
                        self.token,
                        html_url=self.html_url,
                    )
                except GitHubError as e:
                    if e.kind == "not_found":
                        raise
                    info = {
                        "owner": self.owner,
                        "repo": self.repo,
                        "title": self.repo,
                        "description": "",
                        "html_url": self.html_url
                        or f"https://github.com/{self.owner}/{self.repo}",
                    }
                self.finished_add.emit((info, latest), None)
            except Exception as e:
                self.finished_add.emit(None, str(e))

    class CheckUpdatesWorker(QThread):
        finished_check = pyqtSignal(list, object)

        def __init__(
            self,
            net: HttpNet,
            snapshot: List[Tuple[str, str, str, bool, str]],
            token: str,
        ) -> None:
            super().__init__()
            self.net = net
            self.snapshot = snapshot
            self.token = token

        def run(self) -> None:
            results: List[Tuple[str, Optional[Dict[str, Any]], Optional[str]]] = []
            for pkey, owner, repo, inc, html_url in self.snapshot:
                try:
                    rel = get_latest(
                        self.net, owner, repo, self.token, inc, html_url=html_url
                    )
                    results.append((pkey, rel, None))
                except GitHubError as e:
                    results.append((pkey, None, str(e)))
                    if e.kind == "rate_limit":
                        break
                except Exception as e:
                    results.append((pkey, None, str(e)))
            self.finished_check.emit(results, self.net.rate_remaining)

    class ColumnOrderDialog(QDialog):
        """Dialog to reorder table columns via buttons or drag-and-drop."""

        def __init__(
            self,
            parent: QWidget,
            pal: Dict[str, str],
            current_order: List[str],
        ) -> None:
            super().__init__(parent)
            self.setWindowTitle("Column Order")
            self.setFixedSize(390, 390)
            self.pal = pal
            self.col_titles = {cid: title for cid, title in COLS}
            self.saved_order: List[str] = normalize_col_order(current_order)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(14, 14, 14, 14)
            layout.setSpacing(10)

            hint = QLabel(
                "Drag items or use the buttons below to change the left-to-right "
                "column order (you can also drag column headers directly in the table)."
            )
            hint.setWordWrap(True)
            hint.setStyleSheet(f"color: {pal['sub_fg']}; font-size: 12px;")
            layout.addWidget(hint)

            mid = QHBoxLayout()
            mid.setSpacing(10)

            self.list_widget = QListWidget(self)
            self.list_widget.setDragDropMode(
                QAbstractItemView.DragDropMode.InternalMove
            )
            self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
            self.list_widget.setStyleSheet(
                f"QListWidget {{ background-color: {pal['field']}; color: {pal['fg']}; "
                f"border: 1px solid {pal['border']}; border-radius: 4px; padding: 2px; }}"
                f"QListWidget::item {{ padding: 4px 6px; }}"
                f"QListWidget::item:selected {{ background-color: {pal['sel_bg']}; color: {pal['sel_fg']}; }}"
            )
            mid.addWidget(self.list_widget, 1)

            side_btns = QVBoxLayout()
            side_btns.setSpacing(6)

            up_btn = QPushButton("▲  Move Left")
            up_btn.setFixedHeight(28)
            up_btn.clicked.connect(self._move_up)
            side_btns.addWidget(up_btn)

            down_btn = QPushButton("▼  Move Right")
            down_btn.setFixedHeight(28)
            down_btn.clicked.connect(self._move_down)
            side_btns.addWidget(down_btn)

            top_btn = QPushButton("⤒  Far Left")
            top_btn.setFixedHeight(28)
            top_btn.clicked.connect(self._move_top)
            side_btns.addWidget(top_btn)

            bot_btn = QPushButton("⤓  Far Right")
            bot_btn.setFixedHeight(28)
            bot_btn.clicked.connect(self._move_bottom)
            side_btns.addWidget(bot_btn)

            side_btns.addStretch(1)

            reset_btn = QPushButton("Reset Default")
            reset_btn.setFixedHeight(28)
            reset_btn.clicked.connect(self._reset_default)
            side_btns.addWidget(reset_btn)

            mid.addLayout(side_btns)
            layout.addLayout(mid, 1)

            btns = QHBoxLayout()
            btns.addStretch(1)
            save_btn = QPushButton("Apply")
            save_btn.setFixedSize(84, 28)
            save_btn.setDefault(True)
            save_btn.clicked.connect(self._on_save)
            btns.addWidget(save_btn)

            cancel_btn = QPushButton("Cancel")
            cancel_btn.setFixedSize(84, 28)
            cancel_btn.clicked.connect(self.reject)
            btns.addWidget(cancel_btn)
            layout.addLayout(btns)

            self._populate(self.saved_order)

        def _populate(self, order: List[str]) -> None:
            self.list_widget.clear()
            for cid in normalize_col_order(order):
                item = QListWidgetItem(self.col_titles.get(cid, cid))
                item.setData(Qt.ItemDataRole.UserRole, cid)
                self.list_widget.addItem(item)
            if self.list_widget.count() > 0:
                self.list_widget.setCurrentRow(0)

        def _move_up(self) -> None:
            row = self.list_widget.currentRow()
            if row > 0:
                item = self.list_widget.takeItem(row)
                self.list_widget.insertItem(row - 1, item)
                self.list_widget.setCurrentRow(row - 1)

        def _move_down(self) -> None:
            row = self.list_widget.currentRow()
            if 0 <= row < self.list_widget.count() - 1:
                item = self.list_widget.takeItem(row)
                self.list_widget.insertItem(row + 1, item)
                self.list_widget.setCurrentRow(row + 1)

        def _move_top(self) -> None:
            row = self.list_widget.currentRow()
            if row > 0:
                item = self.list_widget.takeItem(row)
                self.list_widget.insertItem(0, item)
                self.list_widget.setCurrentRow(0)

        def _move_bottom(self) -> None:
            row = self.list_widget.currentRow()
            cnt = self.list_widget.count()
            if 0 <= row < cnt - 1:
                item = self.list_widget.takeItem(row)
                self.list_widget.insertItem(cnt - 1, item)
                self.list_widget.setCurrentRow(cnt - 1)

        def _reset_default(self) -> None:
            self._populate(list(DEFAULT_COL_ORDER))

        def _on_save(self) -> None:
            order: List[str] = []
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item is not None:
                    cid = item.data(Qt.ItemDataRole.UserRole)
                    if isinstance(cid, str):
                        order.append(cid)
            self.saved_order = normalize_col_order(order)
            self.accept()

    class AboutDialog(QDialog):
        def __init__(self, parent: QWidget, pal: Dict[str, str]) -> None:
            super().__init__(parent)
            self.setWindowTitle(f"About {APP_NAME}")
            self.setFixedSize(430, 196)
            self.pal = pal

            layout = QVBoxLayout(self)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(10)

            top = QHBoxLayout()
            icon_lbl = QLabel("GRT")
            icon_lbl.setFixedSize(48, 48)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setStyleSheet(
                f"background-color: {pal['sel_bg']}; color: {pal['sel_fg']}; "
                "font-weight: bold; font-size: 15px; border-radius: 8px;"
            )
            top.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignTop)

            info_col = QVBoxLayout()
            info_col.setSpacing(4)
            head = QLabel(APP_NAME)
            head_font = QFont("Segoe UI", 13)
            head_font.setBold(True)
            head.setFont(head_font)
            info_col.addWidget(head)

            ver = QLabel(f"Version {APP_VERSION} (Portable Single-File PyQt6)")
            info_col.addWidget(ver)

            desc = QLabel(
                "Tracks the latest release of the GitHub, Forgejo/Gitea, and web "
                "projects you follow. No account, login or token needed. MIT License."
            )
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {pal['sub_fg']};")
            info_col.addWidget(desc)

            link = QLabel(
                f'<a href="{REPO_URL}" style="color: {pal["link"]};">{REPO_URL}</a>'
            )
            link.setOpenExternalLinks(True)
            info_col.addWidget(link)

            top.addLayout(info_col, 1)
            layout.addLayout(top)
            layout.addStretch(1)

            btns = QHBoxLayout()
            btns.addStretch(1)
            copy_btn = QPushButton("Copy version")
            copy_btn.setFixedSize(96, 28)
            copy_btn.clicked.connect(self._copy_version)
            btns.addWidget(copy_btn)

            close_btn = QPushButton("Close")
            close_btn.setFixedSize(84, 28)
            close_btn.setDefault(True)
            close_btn.clicked.connect(self.accept)
            btns.addWidget(close_btn)
            layout.addLayout(btns)

        def _copy_version(self) -> None:
            text = f"{APP_NAME} v{APP_VERSION}"
            cb = QApplication.clipboard()
            if cb:
                cb.setText(text)

    class SettingsDialog(QDialog):
        def __init__(
            self,
            parent: QWidget,
            pal: Dict[str, str],
            token: str,
            check_on_launch: bool,
        ) -> None:
            super().__init__(parent)
            self.setWindowTitle("Settings")
            self.setFixedSize(440, 236)
            self.pal = pal
            self.saved_token = token
            self.saved_launch = check_on_launch

            layout = QVBoxLayout(self)
            layout.setContentsMargins(14, 14, 14, 14)
            layout.setSpacing(10)

            lbl = QLabel("GitHub personal access token (optional)")
            layout.addWidget(lbl)

            self.token_edit = QLineEdit(token)
            self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.token_edit.setMaxLength(200)
            self.token_edit.setFixedHeight(28)
            layout.addWidget(self.token_edit)

            note = QLabel(
                "Not needed for normal use: releases are read from public feeds. "
                "A token only helps if the GitHub feed is blocked or for stable-only mode. "
                "It is stored in plain text in projects.json next to this script and is never written to exported files."
            )
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {pal['sub_fg']}; font-size: 12px;")
            layout.addWidget(note)

            self.launch_cb = QCheckBox("Check for updates when the app starts")
            self.launch_cb.setChecked(check_on_launch)
            layout.addWidget(self.launch_cb)

            layout.addStretch(1)

            btns = QHBoxLayout()
            about_btn = QPushButton("About")
            about_btn.setFixedSize(84, 28)
            about_btn.clicked.connect(self._show_about)
            btns.addWidget(about_btn)

            btns.addStretch(1)

            save_btn = QPushButton("Save")
            save_btn.setFixedSize(84, 28)
            save_btn.setDefault(True)
            save_btn.clicked.connect(self._on_save)
            btns.addWidget(save_btn)

            cancel_btn = QPushButton("Cancel")
            cancel_btn.setFixedSize(84, 28)
            cancel_btn.clicked.connect(self.reject)
            btns.addWidget(cancel_btn)
            layout.addLayout(btns)

        def _show_about(self) -> None:
            dlg = AboutDialog(self, self.pal)
            dlg.exec()

        def _on_save(self) -> None:
            self.saved_token = self.token_edit.text().strip()[:200]
            self.saved_launch = self.launch_cb.isChecked()
            self.accept()

    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.data_path = data_file_path()
            self.data = load_data(self.data_path)
            theme_pref = self.data["settings"].get("theme", "")
            if theme_pref == "dark":
                self.dark = True
            elif theme_pref == "light":
                self.dark = False
            else:
                self.dark = detect_system_dark()

            self.net = HttpNet()
            self.busy = False
            self.suppress_events = True
            self.col_widths = normalize_col_widths(
                self.data["settings"].get("col_widths")
            )
            self.col_order = normalize_col_order(
                self.data["settings"].get("col_order")
            )
            self._last_section_moved_ts = 0.0
            self.search_query = ""
            self.view_indices: List[int] = []
            self.view_keys: List[str] = []
            self.worker: Optional[QThread] = None

            self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
            self.resize(1480, 560)
            self.setMinimumSize(940, 340)

            icon_path = ensure_portable_icon()
            if icon_path and icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))

            central = QWidget(self)
            self.setCentralWidget(central)
            root = QVBoxLayout(central)
            root.setContentsMargins(10, 10, 10, 8)
            root.setSpacing(6)

            # Row 1: Project URL / owner/repo entry + Add project + Top Search Bar across all columns
            row1 = QHBoxLayout()
            row1.setSpacing(8)
            self.entry_label = QLabel("Project (GitHub/Forgejo URL, download page, or owner/repo):")
            row1.addWidget(self.entry_label)

            self.entry_edit = QLineEdit()
            self.entry_edit.setMaxLength(300)
            self.entry_edit.setFixedHeight(28)
            self.entry_edit.setPlaceholderText(
                "owner/repo, https://git.magicbean.dev/MagicBeanDev/Longshot, or https://eden-emu.dev/downloads/"
            )
            self.entry_edit.returnPressed.connect(self.add_project)
            row1.addWidget(self.entry_edit, 3)

            self.add_btn = QPushButton("+  Add project")
            self.add_btn.setFixedHeight(28)
            self.add_btn.clicked.connect(self.add_project)
            row1.addWidget(self.add_btn)

            self.search_label = QLabel("🔍 Search:")
            row1.addWidget(self.search_label)

            self.search_edit = QLineEdit()
            self.search_edit.setMaxLength(200)
            self.search_edit.setFixedHeight(28)
            self.search_edit.setMinimumWidth(220)
            self.search_edit.setClearButtonEnabled(True)
            self.search_edit.setPlaceholderText(
                "Search all columns (Title, Project, Repo, Source, Target, Release, Status, Comment)..."
            )
            self.search_edit.setToolTip(
                "Filter projects by keyword across all 10 columns (Ctrl+F)"
            )
            self.search_edit.textChanged.connect(self.on_search_changed)
            row1.addWidget(self.search_edit, 2)

            self.search_count_lbl = QLabel("")
            self.search_count_lbl.setFixedHeight(28)
            self.search_count_lbl.setVisible(False)
            row1.addWidget(self.search_count_lbl)

            root.addLayout(row1)

            # Row 2: Toolbar buttons
            row2 = QHBoxLayout()
            row2.setSpacing(8)

            self.check_btn = QPushButton("↻  Check for updates")
            self.check_btn.setFixedHeight(30)
            self.check_btn.clicked.connect(self.check_updates)
            row2.addWidget(self.check_btn)

            self.seen_btn = QPushButton("☑  Mark as seen")
            self.seen_btn.setFixedHeight(30)
            self.seen_btn.clicked.connect(self.mark_seen)
            row2.addWidget(self.seen_btn)

            self.open_btn = QPushButton("↗  Open release page")
            self.open_btn.setFixedHeight(30)
            self.open_btn.clicked.connect(self.open_release)
            row2.addWidget(self.open_btn)

            self.remove_btn = QPushButton("🗑  Remove")
            self.remove_btn.setFixedHeight(30)
            self.remove_btn.clicked.connect(self.remove_selected)
            row2.addWidget(self.remove_btn)

            row2.addStretch(1)

            self.columns_btn = QPushButton("⇄  Columns")
            self.columns_btn.setFixedHeight(30)
            self.columns_btn.setToolTip(
                "Change column order (you can also drag column headers directly)"
            )
            self.columns_btn.clicked.connect(self.show_column_order_dialog)
            row2.addWidget(self.columns_btn)

            self.import_btn = QPushButton("📥  Import")
            self.import_btn.setFixedHeight(30)
            self.import_btn.clicked.connect(self.import_json)
            row2.addWidget(self.import_btn)

            self.export_btn = QPushButton("📤  Export")
            self.export_btn.setFixedHeight(30)
            self.export_btn.clicked.connect(self.export_json)
            row2.addWidget(self.export_btn)

            self.settings_btn = QPushButton("⚙  Settings")
            self.settings_btn.setFixedHeight(30)
            self.settings_btn.clicked.connect(self.show_settings)
            row2.addWidget(self.settings_btn)
            root.addLayout(row2)

            # Row 3: 10-Column Table (Title, Project, Repository, Source, Target, Current release, Published, Status, Last checked, Comment)
            self.table = QTableWidget(0, len(COLS), self)
            self.table.setHorizontalHeaderLabels([title for _, title in COLS])
            self.table.verticalHeader().setVisible(False)
            self.table.verticalHeader().setDefaultSectionSize(28)
            self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.table.customContextMenuRequested.connect(self.on_table_context_menu)
            self.table.itemSelectionChanged.connect(self.on_selection_changed)
            self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
            self.table.itemChanged.connect(self.on_item_changed)

            header = self.table.horizontalHeader()
            header.setSectionsClickable(True)
            header.setSectionsMovable(True)
            if hasattr(header, "setFirstSectionMovable"):
                header.setFirstSectionMovable(True)
            header.setHighlightSections(False)
            header.setStretchLastSection(False)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            header.customContextMenuRequested.connect(self.on_header_context_menu)
            header.sectionClicked.connect(self.on_header_clicked)
            header.sectionResized.connect(self.on_section_resized)
            header.sectionMoved.connect(self.on_section_moved)

            root.addWidget(self.table, 1)

            # Row 4: Status bar + Moon/Sun theme toggle button
            row4 = QHBoxLayout()
            row4.setSpacing(8)
            self.status_lbl = QLabel("Add a project to get started.")
            self.status_lbl.setFixedHeight(26)
            self.status_lbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.status_lbl.customContextMenuRequested.connect(self.on_status_context_menu)
            row4.addWidget(self.status_lbl, 1)

            self.theme_btn = QPushButton("☀" if self.dark else "☾")
            self.theme_btn.setFixedSize(28, 28)
            self.theme_btn.setToolTip(
                "Switch to light mode" if self.dark else "Switch to dark mode"
            )
            self.theme_btn.clicked.connect(self.toggle_theme)
            row4.addWidget(self.theme_btn)
            root.addLayout(row4)

            # Keyboard shortcuts (Delete, F2, Ctrl+F)
            del_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
            del_shortcut.activated.connect(self.on_delete_key)
            f2_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F2), self.table)
            f2_shortcut.activated.connect(self.rename_selected)
            find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
            find_shortcut.activated.connect(self.focus_search)

            self.apply_theme()
            self.update_headings()
            self.render_table()
            self.restore_saved_columns()
            self.suppress_events = False

            if self.data["projects"]:
                updates = sum(1 for p in self.data["projects"] if has_update(p))
                if updates > 0:
                    self.set_status(
                        f"{len(self.data['projects'])} project(s) loaded: {updates} update(s) available."
                    )
                else:
                    self.set_status(f"{len(self.data['projects'])} project(s) loaded.")

            if self.data["settings"].get("check_on_launch") and self.data["projects"]:
                self.check_updates()

        def focus_search(self) -> None:
            self.search_edit.setFocus()
            self.search_edit.selectAll()

        def on_search_changed(self, text: str) -> None:
            self.search_query = text
            self.render_table()
            q = text.strip()
            total = len(self.data["projects"])
            matched = len(self.view_indices)
            if q:
                self.search_count_lbl.setText(f"{matched} / {total}")
                self.search_count_lbl.setVisible(True)
                self.set_status(
                    f"Showing {matched} of {total} project(s) matching '{q}'."
                )
            else:
                self.search_count_lbl.setText("")
                self.search_count_lbl.setVisible(False)
                self.set_status(f"Showing all {total} project(s).")

        def on_delete_key(self) -> None:
            """Handle Delete key without interrupting active text editing in a QLineEdit."""
            fw = QApplication.focusWidget()
            if isinstance(fw, QLineEdit) and fw.hasFocus():
                return
            self.remove_selected()

        def pal(self) -> Dict[str, str]:
            return get_palette(self.dark)

        def apply_theme(self) -> None:
            p = self.pal()
            self.theme_btn.setText("☀" if self.dark else "☾")
            self.theme_btn.setToolTip(
                "Switch to light mode" if self.dark else "Switch to dark mode"
            )
            self.setStyleSheet(
                f"""
                QMainWindow, QDialog, QWidget {{
                    background-color: {p['bg']};
                    color: {p['fg']};
                    font-family: "Segoe UI", sans-serif;
                    font-size: 13px;
                }}
                QLineEdit {{
                    background-color: {p['field']};
                    color: {p['fg']};
                    border: 1px solid {p['border']};
                    border-radius: 4px;
                    padding: 2px 8px;
                }}
                QLineEdit:focus {{
                    border: 1px solid {p['sel_bg']};
                }}
                QPushButton {{
                    background-color: {p['btn_bg']};
                    color: {p['fg']};
                    border: 1px solid {p['border']};
                    border-radius: 4px;
                    padding: 2px 12px;
                }}
                QPushButton:pressed {{
                    background-color: {p['btn_active']};
                }}
                QPushButton:disabled {{
                    color: {p['none_fg']};
                }}
                QTableWidget {{
                    background-color: {p['field']};
                    color: {p['fg']};
                    gridline-color: {p['line']};
                    border: 1px solid {p['border']};
                    selection-background-color: {p['sel_bg']};
                    selection-color: {p['sel_fg']};
                }}
                QHeaderView::section {{
                    background-color: {p['head_bg']};
                    color: {p['fg']};
                    font-weight: bold;
                    border: none;
                    border-right: 1px solid {p['line']};
                    border-bottom: 1px solid {p['line']};
                    padding: 4px 6px;
                }}
                QComboBox {{
                    background-color: {p['field']};
                    color: {p['fg']};
                    border: 1px solid {p['border']};
                    border-radius: 3px;
                    padding: 1px 6px;
                }}
                QComboBox QAbstractItemView {{
                    background-color: {p['field']};
                    color: {p['fg']};
                    selection-background-color: {p['sel_bg']};
                    selection-color: {p['sel_fg']};
                }}
                QMenu {{
                    background-color: {p['field']};
                    color: {p['fg']};
                    border: 1px solid {p['border']};
                }}
                QMenu::item:selected {{
                    background-color: {p['sel_bg']};
                    color: {p['sel_fg']};
                }}
                """
            )
            self.render_table()

        def toggle_theme(self) -> None:
            self.dark = not self.dark
            self.data["settings"]["theme"] = "dark" if self.dark else "light"
            self.persist()
            self.apply_theme()
            self.set_status("Dark mode" if self.dark else "Light mode")

        def apply_col_order(self, order: List[str]) -> None:
            """Reorder QHeaderView visual sections to match the given column ID order."""
            norm_order = normalize_col_order(order)
            prev = self.suppress_events
            self.suppress_events = True
            try:
                header = self.table.horizontalHeader()
                id_to_logical = {cid: idx for idx, (cid, _) in enumerate(COLS)}
                for target_vis, cid in enumerate(norm_order):
                    logical_idx = id_to_logical[cid]
                    curr_vis = header.visualIndex(logical_idx)
                    if curr_vis != target_vis and curr_vis >= 0:
                        header.moveSection(curr_vis, target_vis)
                self.col_order = norm_order
                self.data["settings"]["col_order"] = list(norm_order)
            finally:
                self.suppress_events = prev

        def restore_saved_columns(self) -> None:
            """Apply the saved column order and column widths loaded from projects.json."""
            prev = self.suppress_events
            self.suppress_events = True
            try:
                self.apply_col_order(self.col_order)
                header = self.table.horizontalHeader()
                for i, w in enumerate(self.col_widths):
                    width = max(COL_MIN[i], int(w))
                    self.table.setColumnWidth(i, width)
                    header.resizeSection(i, width)
            finally:
                self.suppress_events = prev

        def save_current_column_widths(self) -> None:
            """Capture current QTableWidget column widths and column order into settings and persist."""
            header = self.table.horizontalHeader()
            widths: List[int] = []
            for i in range(len(COLS)):
                w = header.sectionSize(i)
                if w <= 0:
                    w = self.col_widths[i]
                widths.append(max(COL_MIN[i], int(w)))
            order: List[str] = []
            for vis in range(len(COLS)):
                log_idx = header.logicalIndex(vis)
                if 0 <= log_idx < len(COLS):
                    order.append(COLS[log_idx][0])
            self.col_widths = widths
            self.col_order = normalize_col_order(order)
            self.data["settings"]["col_widths"] = list(widths)
            self.data["settings"]["col_order"] = list(self.col_order)
            self.persist()

        def closeEvent(self, event: Any) -> None:
            """Save column widths, column order, and application state to projects.json on exit."""
            self.save_current_column_widths()
            super().closeEvent(event)

        def on_section_resized(self, logical_index: int, _old: int, new_size: int) -> None:
            if self.suppress_events:
                return
            if 0 <= logical_index < len(self.col_widths) and new_size > 0:
                self.col_widths[logical_index] = max(COL_MIN[logical_index], int(new_size))
                self.data["settings"]["col_widths"] = list(self.col_widths)
                self.persist()

        def on_section_moved(
            self, logical_index: int, _old_visual: int, new_visual: int
        ) -> None:
            if self.suppress_events:
                return
            self._last_section_moved_ts = time.monotonic()
            self.save_current_column_widths()
            if 0 <= logical_index < len(COLS):
                col_title = COLS[logical_index][1]
                self.set_status(
                    f"Moved '{col_title}' column to position {new_visual + 1}."
                )

        def move_column_visual(self, from_vis: int, to_vis: int) -> None:
            if not (0 <= from_vis < len(COLS) and 0 <= to_vis < len(COLS)):
                return
            if from_vis == to_vis:
                return
            header = self.table.horizontalHeader()
            header.moveSection(from_vis, to_vis)

        def reset_column_order(self) -> None:
            self.apply_col_order(list(DEFAULT_COL_ORDER))
            self.save_current_column_widths()
            self.set_status("Column order reset to default.")

        def show_column_order_dialog(self) -> None:
            dlg = ColumnOrderDialog(self, self.pal(), self.col_order)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.apply_col_order(dlg.saved_order)
                self.save_current_column_widths()
                self.set_status("Column order updated.")

        def on_header_context_menu(self, pos: Any) -> None:
            header = self.table.horizontalHeader()
            logical_idx = header.logicalIndexAt(pos)
            menu = QMenu(self)

            if 0 <= logical_idx < len(COLS):
                vis_idx = header.visualIndex(logical_idx)
                col_title = COLS[logical_idx][1]

                act_left = QAction(f"Move '{col_title}' Left", self)
                act_left.setEnabled(vis_idx > 0)
                act_left.triggered.connect(
                    lambda _checked=False, v=vis_idx: self.move_column_visual(v, v - 1)
                )
                menu.addAction(act_left)

                act_right = QAction(f"Move '{col_title}' Right", self)
                act_right.setEnabled(vis_idx < len(COLS) - 1)
                act_right.triggered.connect(
                    lambda _checked=False, v=vis_idx: self.move_column_visual(v, v + 1)
                )
                menu.addAction(act_right)

                act_first = QAction(f"Move '{col_title}' to Far Left", self)
                act_first.setEnabled(vis_idx > 0)
                act_first.triggered.connect(
                    lambda _checked=False, v=vis_idx: self.move_column_visual(v, 0)
                )
                menu.addAction(act_first)

                act_last = QAction(f"Move '{col_title}' to Far Right", self)
                act_last.setEnabled(vis_idx < len(COLS) - 1)
                act_last.triggered.connect(
                    lambda _checked=False, v=vis_idx: self.move_column_visual(
                        v, len(COLS) - 1
                    )
                )
                menu.addAction(act_last)
                menu.addSeparator()

            act_dlg = QAction("Configure Column Order...", self)
            act_dlg.triggered.connect(self.show_column_order_dialog)
            menu.addAction(act_dlg)

            act_reset = QAction("Reset Column Order to Default", self)
            act_reset.setEnabled(list(self.col_order) != list(DEFAULT_COL_ORDER))
            act_reset.triggered.connect(self.reset_column_order)
            menu.addAction(act_reset)

            menu.exec(header.mapToGlobal(pos))

        def selected_keys(self) -> List[str]:
            rows = sorted({idx.row() for idx in self.table.selectedIndexes()})
            if not rows and self.table.currentRow() >= 0:
                rows = [self.table.currentRow()]
            existing_keys = {project_key(p) for p in self.data["projects"]}
            keys: List[str] = []
            for r in rows:
                if 0 <= r < len(self.view_keys):
                    k = self.view_keys[r]
                    if k in existing_keys and k not in keys:
                        keys.append(k)
            return keys

        def update_headings(self) -> None:
            sort_col = self.data["settings"].get("sort_col", "")
            sort_asc = self.data["settings"].get("sort_asc", True)
            labels: List[str] = []
            for cid, title in COLS:
                if cid == sort_col:
                    arrow = " ▲" if sort_asc else " ▼"
                    labels.append(f"{title}{arrow}")
                else:
                    labels.append(title)
            self.table.setHorizontalHeaderLabels(labels)
            for i in range(len(COLS)):
                hi = self.table.horizontalHeaderItem(i)
                if hi is not None:
                    hi.setToolTip(
                        "Click to sort • Drag header or right-click to change column order"
                    )

        def on_header_clicked(self, col_idx: int) -> None:
            if time.monotonic() - self._last_section_moved_ts < 0.25:
                return
            if not (0 <= col_idx < len(COLS)):
                return
            cid = COLS[col_idx][0]
            if cid not in SORTABLE:
                return
            if self.data["settings"].get("sort_col") == cid:
                self.data["settings"]["sort_asc"] = not self.data["settings"].get(
                    "sort_asc", True
                )
            else:
                self.data["settings"]["sort_col"] = cid
                self.data["settings"]["sort_asc"] = cid != "published"
            self.persist()
            self.update_headings()
            self.render_table()

        def _clear_table_widgets(self) -> None:
            """Safely detach cell widgets and clear focus before shrinking or rebuilding rows."""
            fw = QApplication.focusWidget()
            if fw is not None and (fw is self.table or self.table.isAncestorOf(fw)):
                self.entry_edit.setFocus()
            rows = self.table.rowCount()
            cols = self.table.columnCount()
            for r in range(rows):
                for c in range(cols):
                    w = self.table.cellWidget(r, c)
                    if w is not None:
                        w.blockSignals(True)
                        filt = getattr(w, "_row_filter", None)
                        if filt is not None:
                            w.removeEventFilter(filt)
                            setattr(w, "_row_filter", None)
                        self.table.removeCellWidget(r, c)
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)
            self.table.setRowCount(0)

        def _attach_row_filter(self, widget: QWidget, row: int) -> None:
            filt = RowSelectFilter(self, widget, row)
            setattr(widget, "_row_filter", filt)
            widget.installEventFilter(filt)

        def render_table(self) -> None:
            keep = set(self.selected_keys())
            prev_suppress = self.suppress_events
            self.suppress_events = True
            try:
                self._clear_table_widgets()
                sorted_indices = sort_order(
                    self.data["projects"],
                    self.data["settings"].get("sort_col", ""),
                    self.data["settings"].get("sort_asc", True),
                )
                self.view_indices = filter_indices(
                    self.data["projects"], sorted_indices, self.search_query
                )
                self.view_keys = [
                    project_key(self.data["projects"][ix])
                    for ix in self.view_indices
                    if 0 <= ix < len(self.data["projects"])
                ]
                q = self.search_query.strip()
                if q:
                    self.search_count_lbl.setText(
                        f"{len(self.view_indices)} / {len(self.data['projects'])}"
                    )
                    self.search_count_lbl.setVisible(True)
                else:
                    self.search_count_lbl.setText("")
                    self.search_count_lbl.setVisible(False)
                p = self.pal()
                self.table.setRowCount(len(self.view_indices))

                for row, ix in enumerate(self.view_indices):
                    proj = self.data["projects"][ix]
                    pkey = project_key(proj)

                    bg_color = QColor(p["field"])
                    fg_color = QColor(p["fg"])
                    if proj.get("error"):
                        fg_color = QColor(p["error_fg"])
                    elif has_update(proj):
                        bg_color = QColor(p["update_bg"])
                        fg_color = QColor(p["update_fg"])
                    elif not proj.get("latest"):
                        fg_color = QColor(p["none_fg"])

                    texts = [
                        str(proj.get("user_title", "")),
                        display_name(proj),
                        repo_display_label(proj),
                        proj.get("source", "PC"),
                        proj.get("target", "PC"),
                        release_label(proj),
                        published_label(proj),
                        status_text(proj),
                        checked_label(proj),
                        str(proj.get("comment", "")),
                    ]

                    for col, text in enumerate(texts):
                        if col == 0:
                            # Col 0: Free-text Title column
                            title_edit = QLineEdit(text, self.table)
                            title_edit.setMaxLength(MAX_TITLE_LEN)
                            title_edit.setPlaceholderText("Add title...")
                            title_edit.setFrame(False)
                            title_edit.setStyleSheet(
                                f"background: transparent; color: {p['fg']}; border: none; padding: 1px 4px;"
                            )
                            self._attach_row_filter(title_edit, row)
                            title_edit.textEdited.connect(
                                lambda val, k=pkey: self.on_user_title_text_changed(
                                    k, val
                                )
                            )
                            self.table.setCellWidget(row, col, title_edit)
                            bg_item = QTableWidgetItem("")
                            bg_item.setBackground(bg_color)
                            bg_item.setForeground(fg_color)
                            bg_item.setFlags(
                                bg_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                            )
                            self.table.setItem(row, col, bg_item)
                        elif col in (3, 4):
                            # Col 3: Source | Col 4: Target
                            field_name = "source" if col == 3 else "target"
                            choices = (
                                SOURCE_PLATFORMS if col == 3 else TARGET_PLATFORMS
                            )
                            combo = QComboBox(self.table)
                            combo.addItems(list(choices))
                            curr_val = (
                                normalize_source_platform(proj.get(field_name))
                                if col == 3
                                else normalize_target_platform(proj.get(field_name))
                            )
                            combo.setCurrentText(curr_val)
                            self._attach_row_filter(combo, row)
                            combo.currentTextChanged.connect(
                                lambda val, k=pkey, f=field_name: self.on_platform_changed(
                                    k, f, val
                                )
                            )
                            self.table.setCellWidget(row, col, combo)
                        elif col == 9:
                            # Col 9: Free-text Comment column
                            comment_edit = QLineEdit(text, self.table)
                            comment_edit.setMaxLength(MAX_COMMENT_LEN)
                            comment_edit.setPlaceholderText("Add comment...")
                            comment_edit.setFrame(False)
                            comment_edit.setStyleSheet(
                                f"background: transparent; color: {p['fg']}; border: none; padding: 1px 4px;"
                            )
                            self._attach_row_filter(comment_edit, row)
                            comment_edit.textEdited.connect(
                                lambda val, k=pkey: self.on_comment_text_changed(
                                    k, val
                                )
                            )
                            self.table.setCellWidget(row, col, comment_edit)
                            bg_item = QTableWidgetItem("")
                            bg_item.setBackground(bg_color)
                            bg_item.setForeground(fg_color)
                            bg_item.setFlags(
                                bg_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                            )
                            self.table.setItem(row, col, bg_item)
                        else:
                            item = QTableWidgetItem(text)
                            item.setBackground(bg_color)
                            item.setForeground(fg_color)
                            if col == 1:
                                # Col 1: Project name (editable via F2 / double-click)
                                item.setFlags(
                                    item.flags() | Qt.ItemFlag.ItemIsEditable
                                )
                            else:
                                item.setFlags(
                                    item.flags() & ~Qt.ItemFlag.ItemIsEditable
                                )
                            self.table.setItem(row, col, item)

                    if pkey in keep:
                        self.table.selectRow(row)
            finally:
                self.suppress_events = prev_suppress

        def on_user_title_text_changed(self, pkey: str, text: str) -> None:
            if self.suppress_events:
                return
            for proj in self.data["projects"]:
                if project_key(proj) == pkey:
                    proj["user_title"] = clean_user_title(text)
                    self.persist()
                    break

        def on_user_title_edited(self, pkey: str, text: str) -> None:
            if self.suppress_events:
                return
            for proj in self.data["projects"]:
                if project_key(proj) == pkey:
                    apply_user_title(proj, text)
                    self.persist()
                    break

        def on_comment_text_changed(self, pkey: str, text: str) -> None:
            if self.suppress_events:
                return
            for proj in self.data["projects"]:
                if project_key(proj) == pkey:
                    proj["comment"] = clean_comment(text)
                    self.persist()
                    break

        def on_comment_edited(self, pkey: str, text: str) -> None:
            if self.suppress_events:
                return
            for proj in self.data["projects"]:
                if project_key(proj) == pkey:
                    apply_comment(proj, text)
                    self.persist()
                    break

        def on_platform_changed(self, pkey: str, field: str, value: str) -> None:
            if self.suppress_events:
                return
            norm = (
                normalize_source_platform(value)
                if field == "source"
                else normalize_target_platform(value)
            )
            for proj in self.data["projects"]:
                if project_key(proj) == pkey:
                    if proj.get(field) != norm:
                        proj[field] = norm
                        self.persist()
                        label = "Source" if field == "source" else "Target"
                        self.set_status(f"{label} set to {norm}.")
                    break

        def set_status(self, text: str) -> None:
            self.status_lbl.setText(text)

        def persist(self) -> None:
            try:
                write_atomic(self.data_path, data_to_json(self.data))
            except Exception as e:
                QMessageBox.critical(self, APP_NAME, f"Could not save projects.json:\n{e}")

        def set_busy(self, busy: bool, status: Optional[str] = None) -> None:
            self.busy = busy
            self.add_btn.setEnabled(not busy)
            self.check_btn.setEnabled(not busy)
            if status:
                self.set_status(status)

        def on_selection_changed(self) -> None:
            if self.suppress_events:
                return
            keys = self.selected_keys()
            if len(keys) == 1:
                for p in self.data["projects"]:
                    if project_key(p) == keys[0]:
                        if p.get("error"):
                            self.set_status(str(p["error"]))
                        elif not p.get("description"):
                            self.set_status(NO_DESCRIPTION)
                        else:
                            self.set_status(str(p["description"]))
                        break

        def add_project(self) -> None:
            if self.busy:
                return
            parsed = parse_project_input(self.entry_edit.text())
            if not parsed:
                QMessageBox.critical(
                    self,
                    APP_NAME,
                    "Enter a GitHub or Forgejo URL such as\n"
                    "https://github.com/owner/repo\n"
                    "https://git.magicbean.dev/MagicBeanDev/Longshot\n"
                    "https://eden-emu.dev/downloads/\n"
                    "or just owner/repo.",
                )
                return
            owner = parsed["owner"]
            repo = parsed["repo"]
            html_url = parsed["html_url"]
            candidate_key = project_key(
                {"owner": owner, "repo": repo, "html_url": html_url}
            )
            if any(project_key(p) == candidate_key for p in self.data["projects"]):
                QMessageBox.information(
                    self, APP_NAME, f"{repo_display_label({'owner': owner, 'repo': repo, 'html_url': html_url})} is already in the list."
                )
                return

            token = self.data["settings"].get("token", "").strip()
            label = repo_display_label({"owner": owner, "repo": repo, "html_url": html_url})
            self.set_busy(True, f"Adding {label} ...")
            worker = AddProjectWorker(self.net, owner, repo, html_url, token)
            worker.finished_add.connect(self._on_project_added)
            self.worker = worker
            worker.start()

        def _on_project_added(self, res: Any, err: Optional[str]) -> None:
            self.set_busy(False)
            if err is not None or res is None:
                self.set_status("Could not add project.")
                QMessageBox.critical(self, APP_NAME, str(err))
                return
            info, latest = res
            p: Dict[str, Any] = {
                "owner": info["owner"],
                "repo": info["repo"],
                "title": info["title"],
                "user_title": "",
                "description": info["description"],
                "html_url": info["html_url"],
                "include_prereleases": True,
                "fmt": 2,
                "latest": latest,
                "seen_id": latest["id"] if isinstance(latest, dict) else None,
                "seen_tag": latest["tag"] if isinstance(latest, dict) else None,
                "last_checked": now_iso(),
                "error": None,
                "comment": "",
                "source": default_platform(),
                "target": default_platform(),
            }
            norm = normalize_project(p)
            if norm:
                p = norm
            if any(project_key(x) == project_key(p) for x in self.data["projects"]):
                self.set_status("Already in the list.")
                return

            self.data["projects"].append(p)
            self.persist()
            self.entry_edit.clear()
            self.render_table()
            if isinstance(latest, dict):
                rel_name = latest.get("tag") or latest.get("name")
                self.set_status(f"Added {p['title']} - current release {rel_name}.")
            else:
                self.set_status(f"Added {p['title']} - it has no published releases yet.")

        def check_updates(self) -> None:
            if self.busy:
                return
            snapshot = [
                (
                    project_key(p),
                    p["owner"],
                    p["repo"],
                    bool(p.get("include_prereleases", True)),
                    str(p.get("html_url") or ""),
                )
                for p in self.data["projects"]
            ]
            if not snapshot:
                self.set_status("Nothing to check - add a project first.")
                return
            token = self.data["settings"].get("token", "").strip()
            self.set_busy(True, f"Checking {len(snapshot)} project(s) ...")
            worker = CheckUpdatesWorker(self.net, snapshot, token)
            worker.finished_check.connect(self._on_updates_checked)
            self.worker = worker
            worker.start()

        def _on_updates_checked(
            self,
            results: List[Tuple[str, Optional[Dict[str, Any]], Optional[str]]],
            rate: Optional[int],
        ) -> None:
            self.set_busy(False)
            now = now_iso()
            errors = 0
            for key, latest, err in results:
                for p in self.data["projects"]:
                    if project_key(p) == key:
                        if err:
                            errors += 1
                        apply_result(p, latest, err, now)
                        break
            self.persist()
            self.render_table()
            updates = sum(1 for p in self.data["projects"] if has_update(p))
            msg = f"Checked {len(results)} project(s): {updates} update(s) available"
            if errors > 0:
                msg += f", {errors} error(s)"
            if rate is not None:
                msg += f". API calls left this hour: {rate}"
            self.set_status(msg + ".")

        def mark_seen(self) -> None:
            keys = set(self.selected_keys())
            if not keys:
                self.set_status("Select one or more projects first.")
                return
            count = 0
            for p in self.data["projects"]:
                if project_key(p) in keys and has_update(p):
                    latest = p.get("latest")
                    if isinstance(latest, dict):
                        p["seen_id"] = latest.get("id")
                        p["seen_tag"] = latest.get("tag")
                        count += 1
            self.persist()
            self.render_table()
            self.set_status(
                f"Marked {count} project(s) as seen."
                if count > 0
                else "No updates to mark in the selection."
            )

        def first_selected(self) -> Optional[Dict[str, Any]]:
            keys = self.selected_keys()
            if not keys:
                return None
            for p in self.data["projects"]:
                if project_key(p) == keys[0]:
                    return p
            return None

        def open_release(self) -> None:
            p = self.first_selected()
            if not p:
                self.set_status("Select a project first.")
                return
            base_html = str(p.get("html_url") or f"https://github.com/{p['owner']}/{p['repo']}")
            fallback = (
                base_html
                if base_html.endswith("/downloads/") or base_html.endswith("/downloads")
                else f"{base_html.rstrip('/')}/releases"
            )
            latest = p.get("latest")
            url = safe_http_url(
                latest.get("url") if isinstance(latest, dict) else None, fallback
            )
            QDesktopServices.openUrl(QUrl(url))

        def open_repo(self) -> None:
            p = self.first_selected()
            if not p:
                return
            url = safe_http_url(
                p.get("html_url"), f"https://github.com/{p['owner']}/{p['repo']}"
            )
            QDesktopServices.openUrl(QUrl(url))

        def toggle_prerelease(self) -> None:
            keys = set(self.selected_keys())
            if not keys:
                return
            first = self.first_selected()
            new_val = not bool(first.get("include_prereleases", True)) if first else True
            for p in self.data["projects"]:
                if project_key(p) in keys:
                    p["include_prereleases"] = new_val
            self.persist()
            self.set_status(
                'Pre-releases included (uses the free release feed). Click "Check for updates" to apply.'
                if new_val
                else 'Stable-only mode uses the REST API. Click "Check for updates" to apply.'
            )

        def remove_selected(self) -> None:
            keys = self.selected_keys()
            if not keys:
                self.set_status("Select a project first.")
                return
            fw = QApplication.focusWidget()
            if fw is not None and (fw is self.table or self.table.isAncestorOf(fw)):
                self.entry_edit.setFocus()
            names_list = [
                display_name(p) for p in self.data["projects"] if project_key(p) in keys
            ]
            names = ", ".join(names_list[:3]) + ("..." if len(names_list) > 3 else "")
            ans = QMessageBox.question(
                self,
                APP_NAME,
                f"Remove {len(keys)} project(s)?\n{names}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
            key_set = set(keys)
            self.data["projects"] = [
                p for p in self.data["projects"] if project_key(p) not in key_set
            ]
            self.view_indices = []
            self.view_keys = []
            self.persist()
            self.render_table()
            self.set_status(f"Removed {len(keys)} project(s).")

        def rename_selected(self) -> None:
            rows = sorted({idx.row() for idx in self.table.selectedIndexes()})
            if len(rows) != 1:
                self.set_status("Select one project to rename.")
                return
            item = self.table.item(rows[0], 1)
            if item:
                self.table.editItem(item)

        def on_item_changed(self, item: QTableWidgetItem) -> None:
            if self.suppress_events or item.column() != 1:
                return
            row = item.row()
            if 0 <= row < len(self.view_indices):
                idx = self.view_indices[row]
                if 0 <= idx < len(self.data["projects"]):
                    proj = self.data["projects"][idx]
                    msg = apply_rename(proj, item.text())
                    self.persist()
                    self.render_table()
                    if msg:
                        self.set_status(msg)

        def reset_names(self) -> None:
            keys = set(self.selected_keys())
            count = 0
            for p in self.data["projects"]:
                if project_key(p) in keys and "custom_name" in p:
                    p.pop("custom_name", None)
                    count += 1
            if count == 0:
                self.set_status("Nothing to reset: the selection has no custom name.")
                return
            self.persist()
            self.render_table()
            self.set_status(f"Reset {count} name(s) to the default name.")

        def on_cell_double_clicked(self, row: int, col: int) -> None:
            if col == 0:
                w = self.table.cellWidget(row, 0)
                if isinstance(w, QLineEdit):
                    w.setFocus()
                    w.selectAll()
            elif col == 1:
                item = self.table.item(row, 1)
                if item:
                    self.table.editItem(item)
            elif col == 9:
                w = self.table.cellWidget(row, 9)
                if isinstance(w, QLineEdit):
                    w.setFocus()
                    w.selectAll()
            elif col not in (3, 4):
                self.open_release()

        def on_table_context_menu(self, pos: Any) -> None:
            idx = self.table.indexAt(pos)
            if idx.isValid():
                selected_rows = {i.row() for i in self.table.selectedIndexes()}
                if idx.row() not in selected_rows:
                    self.table.selectRow(idx.row())
            if not self.selected_keys():
                return
            menu = QMenu(self)
            act_open = QAction("Open release page", self)
            act_open.triggered.connect(self.open_release)
            menu.addAction(act_open)

            act_repo = QAction("Open repository", self)
            act_repo.triggered.connect(self.open_repo)
            menu.addAction(act_repo)

            act_seen = QAction("Mark as seen", self)
            act_seen.triggered.connect(self.mark_seen)
            menu.addAction(act_seen)

            menu.addSeparator()

            act_rename = QAction("Rename...\tF2", self)
            act_rename.setEnabled(len(self.selected_keys()) == 1)
            act_rename.triggered.connect(self.rename_selected)
            menu.addAction(act_rename)

            has_custom = any(
                "custom_name" in p
                for p in self.data["projects"]
                if project_key(p) in set(self.selected_keys())
            )
            act_reset = QAction("Reset name", self)
            act_reset.setEnabled(has_custom)
            act_reset.triggered.connect(self.reset_names)
            menu.addAction(act_reset)

            first = self.first_selected()
            act_pre = QAction("Include pre-releases", self)
            act_pre.setCheckable(True)
            act_pre.setChecked(
                bool(first.get("include_prereleases", True)) if first else True
            )
            act_pre.triggered.connect(self.toggle_prerelease)
            menu.addAction(act_pre)

            menu.addSeparator()

            act_rem = QAction("Remove...\tDel", self)
            act_rem.triggered.connect(self.remove_selected)
            menu.addAction(act_rem)

            menu.exec(self.table.viewport().mapToGlobal(pos))

        def on_status_context_menu(self, pos: Any) -> None:
            menu = QMenu(self)
            act_copy = QAction("Copy", self)
            act_copy.triggered.connect(
                lambda: QApplication.clipboard().setText(self.status_lbl.text())
            )
            menu.addAction(act_copy)
            menu.exec(self.status_lbl.mapToGlobal(pos))

        def import_json(self) -> None:
            path_str, _ = QFileDialog.getOpenFileName(
                self,
                "Import projects (.json)",
                str(app_dir()),
                "JSON files (*.json);;All files (*.*)",
            )
            if not path_str:
                return
            p = Path(path_str)
            try:
                if p.stat().st_size > MAX_IMPORT_BYTES:
                    QMessageBox.critical(
                        self,
                        APP_NAME,
                        "Could not read that file as JSON:\nThe file is larger than 5 MB.",
                    )
                    return
                raw = json.loads(p.read_text(encoding="utf-8").lstrip("\ufeff"))
            except Exception as e:
                QMessageBox.critical(
                    self, APP_NAME, f"Could not read that file as JSON:\n{e}"
                )
                return

            parsed = parse_import(raw)
            if parsed is None:
                QMessageBox.critical(self, APP_NAME, "This file has no project list.")
                return
            projects, skipped = parsed
            if not projects:
                QMessageBox.critical(
                    self, APP_NAME, "No valid projects found in this file."
                )
                return

            note = (
                f" ({skipped} entries skipped as invalid or duplicate)"
                if skipped > 0
                else ""
            )
            ans = QMessageBox.question(
                self,
                APP_NAME,
                f"Found {len(projects)} project(s){note}.\n\n"
                "Yes = Merge: keep your current list and add the new ones\n"
                "No = Replace: discard your current list and use this file\n"
                "Cancel = do nothing",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if ans == QMessageBox.StandardButton.Yes:
                total = len(projects)
                added = merge_projects(self.data["projects"], projects)
                msg = f"Imported: {added} new project(s) added, {total - added} already in the list."
            elif ans == QMessageBox.StandardButton.No:
                self.data["projects"] = projects
                self.view_indices = []
                self.view_keys = []
                msg = f"Imported: list replaced with {len(projects)} project(s)."
            else:
                return

            self.persist()
            self.render_table()
            self.set_status(f'{msg} Click "Check for updates" to refresh them.')

        def export_json(self) -> None:
            if not self.data["projects"]:
                QMessageBox.information(
                    self, APP_NAME, "There are no projects to export yet."
                )
                return
            default_path = str(app_dir() / f"github_release_tracker_{today_ymd()}.json")
            path_str, _ = QFileDialog.getSaveFileName(
                self,
                "Export projects (.json)",
                default_path,
                "JSON files (*.json);;All files (*.*)",
            )
            if not path_str:
                return
            payload = build_export(self.data["projects"], now_iso())
            try:
                write_atomic(
                    Path(path_str), json.dumps(payload, indent=2, ensure_ascii=False)
                )
                self.set_status(
                    f"Exported {len(self.data['projects'])} project(s) to {path_str} (token not included)."
                )
            except Exception as e:
                QMessageBox.critical(self, APP_NAME, f"Could not write the file:\n{e}")

        def show_settings(self) -> None:
            dlg = SettingsDialog(
                self,
                self.pal(),
                self.data["settings"].get("token", ""),
                bool(self.data["settings"].get("check_on_launch", False)),
            )
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.data["settings"]["token"] = dlg.saved_token
                self.data["settings"]["check_on_launch"] = dlg.saved_launch
                self.persist()
                self.set_status("Settings saved.")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    win = MainWindow()
    app.aboutToQuit.connect(win.save_current_column_widths)
    win.show()
    return int(app.exec())


# ===========================================================================
# Built-in Portable Single-File PyInstaller EXE Builder (--build-exe)
# ===========================================================================
def build_portable_exe() -> int:
    """Build dist/GitHubReleaseTracker.exe right next to github_release_tracker.py."""
    here = app_dir()
    script_path = Path(__file__).resolve()
    icon_path = ensure_portable_icon()
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "GitHubReleaseTracker",
        "--distpath",
        str(here / "dist"),
        "--workpath",
        str(here / "build"),
        "--specpath",
        str(here),
    ]
    if icon_path and icon_path.exists():
        cmd.extend(["--icon", str(icon_path)])
    cmd.append(str(script_path))
    print(f"Building standalone executable in {here / 'dist'} ...")
    return subprocess.call(cmd, cwd=str(here))


# ===========================================================================
# Built-in Unit Test Suite (`python github_release_tracker.py --test`)
# ===========================================================================
SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en-US">
  <id>tag:github.com,2008:https://github.com/o/r/releases</id>
  <title>Release notes from r</title>
  <entry>
    <id>tag:github.com,2008:Repository/123/v1.2.3%2Fx</id>
    <updated>2026-11-17T10:20:30Z</updated>
    <link rel="alternate" type="text/html" href="https://github.com/o/r/releases/tag/v1.2.3%2Fx"/>
    <title>Release &amp; more</title>
    <author><name>someone</name></author>
  </entry>
  <entry><id>tag:github.com,2008:Repository/123/old</id><title>old</title></entry>
</feed>"""

SAMPLE_FORGEJO_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Releases for MagicBeanDev/Longshot</title>
  <id>https://git.magicbean.dev/MagicBeanDev/Longshot/releases</id>
  <updated>2026-11-22T08:28:44Z</updated>
  <subtitle>A supported console game, running natively on Windows and Linux</subtitle>
  <link href="https://git.magicbean.dev/MagicBeanDev/Longshot/releases"></link>
  <entry>
    <title>Longshot v3.1.1</title>
    <updated>2026-11-22T02:52:14Z</updated>
    <id>12210: https://git.magicbean.dev/MagicBeanDev/Longshot/releases/tag/v3.1.1</id>
    <content type="html">&lt;p&gt;Release notes&lt;/p&gt;</content>
  </entry>
</feed>"""

SAMPLE_EDEN_DOWNLOADS_HTML = """<!DOCTYPE html>
<html lang="en">
  <head>
    <title>Eden - Downloads</title>
    <meta name="description" content="Download Eden">
    <meta property="og:site_name" content="Eden">
  </head>
  <body>
    <div class="button-group">
      <a href="https://git.eden-emu.dev/eden-emu/eden/releases" class="btn btn-primary">Stable</a>
      <a href="https://git.eden-emu.dev/eden-ci/nightly/releases" class="btn btn-primary">Nightly</a>
    </div>
  </body>
</html>"""


class _MockNet:
    def __init__(self, feed_res: Any) -> None:
        self.feed_res = feed_res
        self.api_routes: List[Tuple[str, Any]] = []
        self.url_routes: Dict[str, str] = {}
        self.calls: List[str] = []
        self.rate_remaining: Optional[int] = None

    def on(self, prefix: str, result: Any) -> "_MockNet":
        self.api_routes.append((prefix, result))
        return self

    def on_url(self, url: str, body: str) -> "_MockNet":
        self.url_routes[url] = body
        return self

    def url_get(
        self, url: str, accept: str = "*/*", token: str = ""
    ) -> Tuple[str, Dict[str, str]]:
        self.calls.append(f"url:{url}")
        if url in self.url_routes:
            return self.url_routes[url], {}
        raise GitHubError.not_found()

    def api_get(self, path: str, token: str = "") -> Any:
        self.calls.append(path)
        for prefix, res in self.api_routes:
            if path.startswith(prefix):
                if isinstance(res, Exception):
                    raise res
                return res
        raise GitHubError.not_found()

    def feed_get(
        self, owner: str, repo: str, base_host: str = "https://github.com"
    ) -> str:
        self.calls.append("feed")
        if isinstance(self.feed_res, Exception):
            raise self.feed_res
        return str(self.feed_res)


class TestPortableTracker(unittest.TestCase):
    def test_portable_directory_and_icon_generation(self) -> None:
        d = app_dir()
        self.assertTrue(d.exists())
        p = data_file_path()
        self.assertEqual(p.name, "projects.json")
        ico = ensure_portable_icon()
        self.assertIsNotNone(ico)
        assert ico is not None
        self.assertTrue(ico.exists())

    def test_title_left_comment_right_and_col_widths_saved(self) -> None:
        self.assertEqual(COLS[0], ("user_title", "Title"))
        self.assertEqual(COLS[1], ("name", "Project"))
        self.assertEqual(COLS[-1], ("comment", "Comment"))
        self.assertEqual(len(COLS), 10)
        p = normalize_project(
            {
                "owner": "o",
                "repo": "r",
                "user_title": "  Zelda Port \n ",
                "comment": "  My free-text note \n here  ",
            }
        )
        assert p is not None
        self.assertEqual(p["user_title"], "Zelda Port")
        self.assertEqual(p["comment"], "My free-text note   here")
        msg_t = apply_user_title(p, "Ocarina Native")
        self.assertIsNotNone(msg_t)
        self.assertEqual(p["user_title"], "Ocarina Native")

        msg_c = apply_comment(p, "Updated note")
        self.assertIsNotNone(msg_c)
        self.assertEqual(p["comment"], "Updated note")

        # Verify 10-column widths persistence round-trip
        custom_widths = [160, 210, 230, 115, 115, 145, 120, 260, 130, 220]
        raw_json = json.dumps(
            {
                "settings": {"col_widths": custom_widths},
                "projects": [p],
            }
        )
        loaded = parse_data(raw_json)
        assert loaded is not None
        self.assertEqual(loaded["settings"]["col_widths"], custom_widths)
        self.assertEqual(loaded["projects"][0]["user_title"], "Ocarina Native")
        self.assertEqual(loaded["projects"][0]["comment"], "Updated note")

        # Verify 9-column legacy col_widths migration prepends Title width
        legacy_9 = [200, 220, 105, 105, 140, 115, 230, 130, 185]
        migrated = normalize_col_widths(legacy_9)
        self.assertEqual(len(migrated), 10)
        self.assertEqual(migrated[0], COL_BASE[0])
        self.assertEqual(migrated[1:], legacy_9)

    def test_parse_repo_and_external_sites(self) -> None:
        def ok(s: str) -> Optional[str]:
            r = parse_repo(s)
            return f"{r[0]}/{r[1]}" if r else None

        self.assertEqual(ok("https://github.com/owner/repo"), "owner/repo")
        self.assertEqual(
            ok("http://www.github.com/owner/repo/releases/tag/v1"), "owner/repo"
        )
        self.assertEqual(ok("github.com/o/r.git"), "o/r")
        self.assertEqual(ok("  owner/repo  "), "owner/repo")
        self.assertEqual(ok("owner/repo.git"), "owner/repo")

        # Forgejo / Gitea external site support
        mb = parse_project_input("https://git.magicbean.dev/MagicBeanDev/Longshot")
        assert mb is not None
        self.assertEqual(mb["kind"], "forge")
        self.assertEqual(mb["owner"], "MagicBeanDev")
        self.assertEqual(mb["repo"], "Longshot")
        self.assertEqual(
            mb["html_url"], "https://git.magicbean.dev/MagicBeanDev/Longshot"
        )

        # Downloads webpage support
        eden = parse_project_input("https://eden-emu.dev/downloads/")
        assert eden is not None
        self.assertEqual(eden["kind"], "web")
        self.assertEqual(eden["owner"], "eden-emu.dev")
        self.assertEqual(eden["repo"], "downloads")
        self.assertEqual(eden["html_url"], "https://eden-emu.dev/downloads/")

        self.assertIsNone(ok("owner"))
        self.assertIsNone(ok("owner/repo/extra"))
        self.assertIsNone(ok(""))
        self.assertIsNone(ok("/repo"))

    def test_forgejo_and_eden_downloads_parsing(self) -> None:
        # 1. Test Forgejo Atom feed (MagicBeanDev/Longshot)
        rel = parse_feed(
            SAMPLE_FORGEJO_FEED,
            "MagicBeanDev",
            "Longshot",
            "https://git.magicbean.dev/MagicBeanDev/Longshot",
        )
        assert rel is not None
        self.assertEqual(rel["tag"], "v3.1.1")
        self.assertEqual(rel["name"], "Longshot v3.1.1")
        self.assertEqual(rel["published_at"], "2026-11-22T02:52:14Z")
        self.assertEqual(
            rel["url"],
            "https://git.magicbean.dev/MagicBeanDev/Longshot/releases/tag/v3.1.1",
        )

        # 2. Test Eden downloads webpage discovery
        linked_forge, direct_rel, meta = extract_releases_from_webpage(
            SAMPLE_EDEN_DOWNLOADS_HTML, "https://eden-emu.dev/downloads/"
        )
        self.assertEqual(meta["title"], "Eden")
        self.assertEqual(meta["description"], "Download Eden")
        self.assertIsNone(direct_rel)
        self.assertEqual(
            linked_forge, ("https://git.eden-emu.dev", "eden-emu", "eden")
        )

    def test_feed_parse(self) -> None:
        r = parse_feed(SAMPLE_FEED, "o", "r")
        assert r is not None
        self.assertEqual(r["tag"], "v1.2.3/x")
        self.assertEqual(r["name"], "Release & more")
        self.assertEqual(r["published_at"], "2026-11-17T10:20:30Z")
        self.assertEqual(r["url"], "https://github.com/o/r/releases/tag/v1.2.3%2Fx")
        self.assertEqual(r["id"], "tag:github.com,2008:Repository/123/v1.2.3%2Fx")
        self.assertEqual(r["source"], "feed")
        self.assertFalse(r["prerelease"])

    def test_get_latest_prefers_feed_and_falls_back(self) -> None:
        net = _MockNet(SAMPLE_FEED)
        r = get_latest(net, "o", "r", "", True)
        assert r is not None
        self.assertEqual(r["source"], "feed")
        self.assertEqual(net.calls, ["feed"])

        rel_api = [
            {"id": 1, "draft": True, "tag_name": "d"},
            {
                "id": 7,
                "tag_name": "v9",
                "name": "Nine",
                "published_at": "2026-01-02T00:00:00Z",
                "html_url": "https://github.com/o/r/releases/tag/v9",
                "prerelease": True,
            },
        ]
        net2 = _MockNet(GitHubError("blocked")).on(
            "/repos/o/r/releases?per_page=10", rel_api
        )
        r2 = get_latest(net2, "o", "r", "", True)
        assert r2 is not None
        self.assertEqual(r2["tag"], "v9")
        self.assertTrue(r2["prerelease"])

        net3 = _MockNet(SAMPLE_FEED).on(
            "/repos/o/r/releases/latest",
            {
                "id": 2,
                "tag_name": "v1.0",
                "name": "",
                "published_at": "",
                "html_url": "https://github.com/o/r/releases/tag/v1.0",
                "prerelease": False,
            },
        )
        r3 = get_latest(net3, "o", "r", "", False)
        assert r3 is not None
        self.assertEqual(r3["tag"], "v1.0")
        self.assertEqual(net3.calls, ["/repos/o/r/releases/latest"])

    def test_update_detection_and_apply_result(self) -> None:
        def rel(rid: Union[int, str], tag: str) -> Dict[str, Any]:
            return {
                "id": rid,
                "tag": tag,
                "name": tag,
                "published_at": "2026-03-01T00:00:00Z",
                "url": "https://github.com/a/b/releases",
                "prerelease": False,
                "source": "feed",
            }

        p = normalize_project(
            {
                "owner": "a",
                "repo": "b",
                "fmt": 2,
                "latest": rel(1, "v1.0"),
                "seen_id": 1,
                "seen_tag": "v1.0",
            }
        )
        assert p is not None
        self.assertFalse(has_update(p))
        self.assertEqual(status_text(p), "Up to date")

        apply_result(p, rel(2, "v1.1"), None, "2026-11-17T12:00:00")
        self.assertTrue(has_update(p))
        self.assertEqual(status_text(p), "Update available: v1.0 -> v1.1")

        apply_result(p, None, "rate limit", "2026-11-17T13:00:00")
        self.assertEqual(p["latest"]["tag"], "v1.1")
        self.assertTrue(status_text(p).startswith("Error:"))

    def test_platform_columns_with_xbox_wii_and_wii_u_source(self) -> None:
        self.assertEqual(
            SOURCE_PLATFORMS,
            (
                "PC",
                "Android",
                "Switch",
                "Switch 2",
                "PS5",
                "PS4",
                "PS3",
                "Xbox",
                "Wii",
                "Wii U",
            ),
        )
        self.assertEqual(
            TARGET_PLATFORMS,
            ("PC", "Android", "Switch", "Switch 2", "PS5", "PS4", "PS3"),
        )
        p = normalize_project({"owner": "o", "repo": "r"})
        assert p is not None
        self.assertEqual(p["source"], "PC")
        self.assertEqual(p["target"], "PC")

        p2 = normalize_project(
            {"owner": "o", "repo": "r", "source": "wii u", "target": "ps5"}
        )
        assert p2 is not None
        self.assertEqual(p2["source"], "Wii U")
        self.assertEqual(p2["target"], "PS5")

        p_wii = normalize_project(
            {"owner": "o", "repo": "r", "source": "wii", "target": "switch 2"}
        )
        assert p_wii is not None
        self.assertEqual(p_wii["source"], "Wii")
        self.assertEqual(p_wii["target"], "Switch 2")

        p3 = normalize_project(
            {"owner": "o", "repo": "r", "source": "xbox", "target": "xbox"}
        )
        assert p3 is not None
        self.assertEqual(p3["source"], "Xbox")
        self.assertEqual(p3["target"], "PC")

    def test_rename_and_import_export(self) -> None:
        p = normalize_project(
            {
                "owner": "o",
                "repo": "r",
                "title": "Orig",
                "user_title": "Custom Left Title",
                "comment": "Test comment",
                "source": "Wii U",
                "target": "PS4",
            }
        )
        assert p is not None
        self.assertEqual(display_name(p), "Orig")
        msg = apply_rename(p, "  My   App ")
        self.assertEqual(msg, "Renamed to My App.")
        self.assertEqual(display_name(p), "My App")

        exp = build_export([p], "2026-11-17T00:00:00")
        text = json.dumps(exp)
        self.assertNotIn("token", text)
        parsed = parse_import(json.loads(text))
        assert parsed is not None
        imported, skipped = parsed
        self.assertEqual(skipped, 0)
        self.assertEqual(imported[0]["custom_name"], "My App")
        self.assertEqual(imported[0]["user_title"], "Custom Left Title")
        self.assertEqual(imported[0]["comment"], "Test comment")
        self.assertEqual(imported[0]["source"], "Wii U")
        self.assertEqual(imported[0]["target"], "PS4")

    def test_sorting_including_title_comment_source_and_target(self) -> None:
        p1 = normalize_project(
            {
                "owner": "a",
                "repo": "z",
                "title": "Zeta",
                "user_title": "B Title",
                "comment": "Beta note",
                "source": "Wii U",
                "target": "PS5",
            }
        )
        p2 = normalize_project(
            {
                "owner": "b",
                "repo": "a",
                "title": "Alpha",
                "user_title": "A Title",
                "comment": "Alpha note",
                "source": "Android",
                "target": "PC",
            }
        )
        assert p1 is not None and p2 is not None
        projs = [p1, p2]
        self.assertEqual(sort_order(projs, "user_title", True), [1, 0])
        self.assertEqual(sort_order(projs, "user_title", False), [0, 1])
        self.assertEqual(sort_order(projs, "comment", True), [1, 0])
        self.assertEqual(sort_order(projs, "comment", False), [0, 1])
        self.assertEqual(sort_order(projs, "source", True), [1, 0])
        self.assertEqual(sort_order(projs, "source", False), [0, 1])
        self.assertEqual(sort_order(projs, "target", True), [1, 0])
        self.assertEqual(sort_order(projs, "target", False), [0, 1])

    def test_column_layout_fills_width(self) -> None:
        w = layout_columns(COL_BASE, COL_MIN, 1600)
        self.assertEqual(sum(w), 1600)
        for a, b in zip(w, COL_MIN):
            self.assertGreaterEqual(a, b)

    def test_column_order_persistence_and_normalization(self) -> None:
        self.assertEqual(list(DEFAULT_COL_ORDER), [cid for cid, _ in COLS])
        custom_order = [
            "source",
            "target",
            "user_title",
            "name",
            "repo",
            "release",
            "published",
            "status",
            "checked",
            "comment",
        ]
        self.assertEqual(normalize_col_order(custom_order), custom_order)
        # Partial or invalid column order is normalized with remaining columns appended
        partial = ["comment", "invalid_col", "name", "comment"]
        norm_partial = normalize_col_order(partial)
        self.assertEqual(len(norm_partial), len(COLS))
        self.assertEqual(norm_partial[0], "comment")
        self.assertEqual(norm_partial[1], "name")

        # Persistence round-trip via parse_data
        raw = json.dumps({"settings": {"col_order": custom_order}, "projects": []})
        loaded = parse_data(raw)
        assert loaded is not None
        self.assertEqual(loaded["settings"]["col_order"], custom_order)

    def test_search_across_all_columns(self) -> None:
        p1 = normalize_project(
            {
                "owner": "Ryubing",
                "repo": "Ryujinx",
                "title": "Ryujinx",
                "user_title": "Handheld Emu",
                "source": "Switch 2",
                "target": "PC",
                "comment": "Check shader cache",
                "latest": {
                    "id": "v1.2.82",
                    "tag": "v1.2.82",
                    "name": "1.2.82",
                    "published_at": "2025-02-18T10:00:00Z",
                    "url": "https://github.com/Ryubing/Ryujinx/releases/tag/v1.2.82",
                    "prerelease": False,
                    "source": "release",
                },
                "seen_id": "v1.2.80",
                "seen_tag": "v1.2.80",
                "last_checked": "2025-02-20T14:30:00Z",
                "fmt": 2,
            }
        )
        p2 = normalize_project(
            {
                "owner": "MagicBeanDev",
                "repo": "Longshot",
                "html_url": "https://git.magicbean.dev/MagicBeanDev/Longshot",
                "title": "Longshot",
                "user_title": "Retro Tool",
                "source": "Wii U",
                "target": "Android",
                "comment": "Forgejo host",
                "latest": {
                    "id": "v0.9.1",
                    "tag": "v0.9.1",
                    "name": "0.9.1",
                    "published_at": "2025-01-11T08:00:00Z",
                    "url": "https://git.magicbean.dev/MagicBeanDev/Longshot/releases/tag/v0.9.1",
                    "prerelease": False,
                    "source": "release",
                },
                "seen_id": "v0.9.1",
                "seen_tag": "v0.9.1",
                "last_checked": "2025-02-19T09:15:00Z",
                "fmt": 2,
            }
        )
        assert p1 is not None and p2 is not None
        projects = [p1, p2]
        base_idx = [0, 1]

        # Matches each of the 10 columns (Title, Project, Repo, Source, Target, Release, Published, Status, Checked, Comment)
        self.assertEqual(filter_indices(projects, base_idx, "Handheld"), [0])       # Col 0: Title
        self.assertEqual(filter_indices(projects, base_idx, "Longshot"), [1])       # Col 1: Project
        self.assertEqual(filter_indices(projects, base_idx, "magicbean.dev"), [1])  # Col 2: Repository
        self.assertEqual(filter_indices(projects, base_idx, "Wii U"), [1])          # Col 3: Source
        self.assertEqual(filter_indices(projects, base_idx, "Android"), [1])        # Col 4: Target
        self.assertEqual(filter_indices(projects, base_idx, "v1.2.82"), [0])        # Col 5: Current release
        self.assertEqual(filter_indices(projects, base_idx, "2025-02-18"), [0])     # Col 6: Published
        self.assertEqual(filter_indices(projects, base_idx, "Update available"), [0])  # Col 7: Status
        self.assertEqual(filter_indices(projects, base_idx, "2025-02-19 09:15"), [1])  # Col 8: Last checked
        self.assertEqual(filter_indices(projects, base_idx, "shader cache"), [0])   # Col 9: Comment
        self.assertEqual(filter_indices(projects, base_idx, ""), [0, 1])


def main() -> int:
    if "--test" in sys.argv:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestPortableTracker)
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        return 0 if result.wasSuccessful() else 1
    if "--build-exe" in sys.argv:
        return build_portable_exe()
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
