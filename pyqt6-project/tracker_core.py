"""Core logic of GitHub Release Tracker (PyQt6 edition).

Contains no GUI code so it can be unit-tested anywhere with standard Python `unittest`.
Supports repo parsing, release lookup (public Atom feed first, GitHub API fallback),
update detection, configurable Source & Target platform columns
(PC, Android, Switch, Switch 2, PS5, PS4, PS3), safe import/export, and sorting.
"""

from __future__ import annotations

import datetime
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

APP_NAME = "GitHub Release Tracker"
APP_VERSION = "2.0.0"
REPO_URL = "https://github.com/santosasarno-code/github-release-tracker-rs"
NO_DESCRIPTION = "No description, website, or topics provided."
MAX_PROJECTS = 500
MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_CUSTOM_NAME = 80

PLATFORMS: Tuple[str, ...] = (
    "PC",
    "Android",
    "Switch",
    "Switch 2",
    "PS5",
    "PS4",
    "PS3",
)

SORTABLE: Tuple[str, ...] = (
    "name",
    "repo",
    "source",
    "target",
    "published",
    "status",
)

COLS: Tuple[Tuple[str, str], ...] = (
    ("name", "Project"),
    ("repo", "Repository"),
    ("source", "Source"),
    ("target", "Target"),
    ("release", "Current release"),
    ("published", "Published"),
    ("status", "Status"),
    ("checked", "Last checked"),
)

COL_BASE: Tuple[int, ...] = (200, 230, 105, 105, 140, 115, 230, 130)
COL_MIN: Tuple[int, ...] = (110, 110, 85, 85, 90, 105, 120, 105)


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


def normalize_platform(value: Any) -> str:
    if isinstance(value, str):
        trimmed = value.strip().lower()
        for p in PLATFORMS:
            if p.lower() == trimmed:
                return p
    return default_platform()


_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def valid_name(s: str) -> bool:
    return bool(isinstance(s, str) and _NAME_RE.match(s))


def _take_name(s: str) -> Tuple[str, str]:
    i = 0
    n = len(s)
    while i < n and (s[i].isalnum() or s[i] in "_.-"):
        i += 1
    return s[:i], s[i:]


def parse_repo(text: str) -> Optional[Tuple[str, str]]:
    """Accept https://github.com/owner/repo[/...] or owner/repo."""
    if not isinstance(text, str):
        return None
    text = text.strip()
    rest = text
    if rest.startswith("https://"):
        rest = rest[8:]
    elif rest.startswith("http://"):
        rest = rest[7:]
    if rest.startswith("www."):
        rest = rest[4:]

    found: Optional[Tuple[str, str]] = None
    if rest.startswith("github.com/"):
        after = rest[len("github.com/") :]
        owner, r1 = _take_name(after)
        if owner and r1.startswith("/"):
            repo, _ = _take_name(r1[1:])
            if repo:
                found = (owner, repo)

    if found is not None:
        owner, repo = found
    else:
        owner, r1 = _take_name(text)
        if not r1.startswith("/"):
            return None
        repo, tail = _take_name(r1[1:])
        if not owner or not repo or tail:
            return None

    if repo.endswith(".git"):
        repo = repo[:-4]
    if not repo or not valid_name(owner) or not valid_name(repo):
        return None
    return owner, repo


def _str_field(v: Any, limit: int) -> str:
    if isinstance(v, str):
        return v.strip()[:limit]
    return ""


def safe_github_url(url: Any, fallback: str) -> str:
    if (
        isinstance(url, str)
        and url.startswith("https://github.com/")
        and len(url) < 500
        and not any(c.isspace() for c in url)
    ):
        return url
    return fallback


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


def now_iso() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def today_ymd() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")


def project_key(p: Dict[str, Any]) -> str:
    return f"{p.get('owner', '')}/{p.get('repo', '')}".lower()


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


def _normalize_release(v: Any, owner: str, repo: str) -> Optional[Dict[str, Any]]:
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
    return {
        "id": rid,
        "tag": tag,
        "name": _str_field(v.get("name"), 300),
        "published_at": _str_field(v.get("published_at"), 40),
        "url": safe_github_url(
            v.get("url"), f"https://github.com/{owner}/{repo}/releases"
        ),
        "prerelease": bool(v.get("prerelease", False)),
        "source": src,
    }


def normalize_project(raw: Any) -> Optional[Dict[str, Any]]:
    if isinstance(raw, str):
        parsed = parse_repo(raw)
        if not parsed:
            return None
        o: Dict[str, Any] = {"owner": parsed[0], "repo": parsed[1]}
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

    proj: Dict[str, Any] = {
        "owner": owner,
        "repo": repo,
        "title": title if title else repo,
        "description": _str_field(o.get("description"), 500),
        "html_url": safe_github_url(
            o.get("html_url"), f"https://github.com/{owner}/{repo}"
        ),
        "include_prereleases": bool(o.get("include_prereleases", True)),
        "fmt": 2 if o.get("fmt") == 2 else None,
        "latest": _normalize_release(o.get("latest"), owner, repo),
        "seen_id": _id_value(o.get("seen_id")),
        "seen_tag": seen_tag if seen_tag else None,
        "last_checked": _str_field(o.get("last_checked"), 40),
        "error": error if error else None,
        "source": normalize_platform(o.get("source")),
        "target": normalize_platform(o.get("target")),
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

    parsed = parse_import(v)
    data["projects"] = parsed[0] if parsed else []
    return data


def data_to_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


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
    elif col == "name":
        idx.sort(
            key=lambda i: (title_key(projects[i]), project_key(projects[i])),
            reverse=not asc,
        )
    elif col == "repo":
        idx.sort(key=lambda i: project_key(projects[i]), reverse=not asc)
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


def layout_columns(base: Tuple[int, ...], low: Tuple[int, ...], avail: int) -> List[int]:
    total_pref = sum(base)
    total_low = sum(low)
    if avail >= total_pref:
        target = [p * avail / total_pref for p in base]
    else:
        t = max(0.0, (avail - total_low) / max(1, total_pref - total_low))
        target = [lo + (p - lo) * t for p, lo in zip(base, low)]
    sizes = [max(lo, int(x)) for x, lo in zip(target, low)]
    status_idx = 6 if len(sizes) > 6 else 4
    if avail >= total_low and len(sizes) > status_idx:
        sizes[status_idx] += max(0, avail - sum(sizes))
    return sizes


# ---------------------------------------------------------------------------
# Atom Feed & GitHub REST API Lookup
# ---------------------------------------------------------------------------
def parse_feed(body: str, owner: str, repo: str) -> Optional[Dict[str, Any]]:
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
    updated = elem_text("updated")

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

    marker = "/releases/tag/"
    tag = ""
    if marker in href:
        tag = urllib.parse.unquote(href.split(marker, 1)[1])
    elif "Repository/" in entry_id:
        r = entry_id.split("Repository/", 1)[1]
        if "/" in r:
            prefix, rest_tag = r.split("/", 1)
            if prefix.isdigit() and rest_tag:
                tag = rest_tag

    if not entry_id and not tag:
        return None

    return {
        "id": entry_id if entry_id else tag,
        "tag": tag,
        "name": title,
        "published_at": updated,
        "url": href if href else f"https://github.com/{owner}/{repo}/releases",
        "prerelease": False,
        "source": "feed",
    }


class HttpNet:
    """Standard-library HTTPS client for GitHub Atom feeds and REST API."""

    def __init__(self) -> None:
        self.rate_remaining: Optional[int] = None

    def api_get(self, path: str, token: str = "") -> Any:
        url = f"https://api.github.com{path}"
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "GitHubReleaseTracker",
        }
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

    def feed_get(self, owner: str, repo: str) -> str:
        url = f"https://github.com/{owner}/{repo}/releases.atom"
        headers = {
            "User-Agent": "GitHubReleaseTracker",
            "Accept": "application/atom+xml, application/xml;q=0.9, */*;q=0.8",
        }
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise GitHubError.not_found()
            if e.code == 429:
                raise GitHubError(
                    "GitHub is rate-limiting the release feed (429). Try again later."
                )
            raise GitHubError(f"Release feed returned HTTP {e.code}.")
        except Exception as e:
            raise GitHubError(f"Network error: {e}")


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


def fetch_repo_info(net: Any, owner: str, repo: str, token: str = "") -> Dict[str, str]:
    d = net.api_get(f"/repos/{owner}/{repo}", token)
    full = str(d.get("full_name") or f"{owner}/{repo}")
    if "/" in full:
        ro, rr = full.split("/", 1)
    else:
        ro, rr = owner, repo
    return {
        "owner": ro,
        "repo": rr,
        "title": str(d.get("name") or rr),
        "description": str(d.get("description") or ""),
        "html_url": str(d.get("html_url") or f"https://github.com/{full}"),
    }


def fetch_latest_release(
    net: Any, owner: str, repo: str, token: str, include_pre: bool
) -> Optional[Dict[str, Any]]:
    if not include_pre:
        try:
            v = net.api_get(f"/repos/{owner}/{repo}/releases/latest", token)
            if isinstance(v, dict):
                return _release_from_api(v)
        except GitHubError as e:
            if e.kind != "not_found":
                raise

    try:
        data = net.api_get(f"/repos/{owner}/{repo}/releases?per_page=10", token)
        if isinstance(data, list):
            for r in data:
                if isinstance(r, dict) and not r.get("draft"):
                    return _release_from_api(r)
    except GitHubError as e:
        if e.kind != "not_found":
            raise

    try:
        tags = net.api_get(f"/repos/{owner}/{repo}/tags?per_page=1", token)
        if isinstance(tags, list) and tags:
            t = tags[0]
            name = str(t.get("name") or "")
            commit = t.get("commit") if isinstance(t.get("commit"), dict) else {}
            sha = str(commit.get("sha") or name)
            return {
                "id": sha,
                "url": f"https://github.com/{owner}/{repo}/releases/tag/{urllib.parse.quote(name, safe='')}",
                "tag": name,
                "name": "",
                "published_at": "",
                "prerelease": False,
                "source": "tag",
            }
    except GitHubError as e:
        if e.kind != "not_found":
            raise
    return None


def get_latest(
    net: Any, owner: str, repo: str, token: str = "", include_pre: bool = True
) -> Optional[Dict[str, Any]]:
    if include_pre:
        try:
            body = net.feed_get(owner, repo)
            rel = parse_feed(body, owner, repo)
            if rel is not None:
                return rel
        except Exception:
            pass
    return fetch_latest_release(net, owner, repo, token, include_pre)
