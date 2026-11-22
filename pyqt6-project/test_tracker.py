"""Unit tests for GitHub Release Tracker (PyQt6 edition) core logic."""

import json
import unittest
from typing import Any, Dict, List, Optional

from tracker_core import (
    COL_BASE,
    COL_MIN,
    MAX_CUSTOM_NAME,
    PLATFORMS,
    GitHubError,
    apply_rename,
    apply_result,
    build_export,
    checked_label,
    clean_name,
    data_to_json,
    display_name,
    get_latest,
    has_update,
    layout_columns,
    merge_projects,
    normalize_platform,
    normalize_project,
    parse_data,
    parse_feed,
    parse_import,
    parse_repo,
    published_label,
    release_label,
    sort_order,
    status_text,
)

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


class MockNet:
    def __init__(self, feed_res: Any) -> None:
        self.feed_res = feed_res
        self.api_routes: List[tuple[str, Any]] = []
        self.calls: List[str] = []
        self.rate_remaining: Optional[int] = None

    def on(self, prefix: str, result: Any) -> "MockNet":
        self.api_routes.append((prefix, result))
        return self

    def api_get(self, path: str, token: str = "") -> Any:
        self.calls.append(path)
        for prefix, res in self.api_routes:
            if path.startswith(prefix):
                if isinstance(res, Exception):
                    raise res
                return res
        raise GitHubError.not_found()

    def feed_get(self, owner: str, repo: str) -> str:
        self.calls.append("feed")
        if isinstance(self.feed_res, Exception):
            raise self.feed_res
        return str(self.feed_res)


class TestTrackerCore(unittest.TestCase):
    def test_parse_repo_cases(self) -> None:
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
        self.assertIsNone(ok("owner"))
        self.assertIsNone(ok("owner/repo/extra"))
        self.assertIsNone(ok("https://example.com/a/b"))
        self.assertIsNone(ok(""))
        self.assertIsNone(ok("/repo"))

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
        net = MockNet(SAMPLE_FEED)
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
        net2 = MockNet(GitHubError.not_found()).on("/repos/o/r/releases?", rel_api)
        r2 = get_latest(net2, "o", "r", "", True)
        assert r2 is not None
        self.assertEqual((r2["id"], r2["tag"], r2["prerelease"], r2["source"]), (7, "v9", True, "release"))

    def test_platform_columns_and_normalization(self) -> None:
        self.assertEqual(
            PLATFORMS,
            ("PC", "Android", "Switch", "Switch 2", "PS5", "PS4", "PS3"),
        )
        for plat in PLATFORMS:
            self.assertEqual(normalize_platform(plat), plat)
            self.assertEqual(normalize_platform(plat.lower()), plat)

        p = normalize_project(
            {"owner": "o", "repo": "r", "source": "Switch 2", "target": "PS5"}
        )
        assert p is not None
        self.assertEqual(p["source"], "Switch 2")
        self.assertEqual(p["target"], "PS5")

        p_def = normalize_project({"owner": "o", "repo": "r", "source": "unknown"})
        assert p_def is not None
        self.assertEqual(p_def["source"], "PC")
        self.assertEqual(p_def["target"], "PC")

    def test_update_detection_and_apply_result(self) -> None:
        p = normalize_project({"owner": "o", "repo": "r"})
        assert p is not None
        p["fmt"] = 2
        p["latest"] = {
            "id": 1,
            "tag": "v1",
            "name": "",
            "published_at": "2026-01-01",
            "url": "",
            "prerelease": False,
            "source": "release",
        }
        p["seen_id"] = 1
        p["seen_tag"] = "v1"
        self.assertFalse(has_update(p))
        self.assertEqual(status_text(p), "Up to date")

        apply_result(
            p,
            {
                "id": 2,
                "tag": "v2",
                "name": "",
                "published_at": "2026-02-01",
                "url": "",
                "prerelease": False,
                "source": "release",
            },
            None,
            "2026-11-19T10:00:00",
        )
        self.assertTrue(has_update(p))
        self.assertEqual(status_text(p), "Update available: v1 -> v2")

    def test_sorting_including_source_and_target(self) -> None:
        a = normalize_project({"owner": "o", "repo": "alpha", "source": "Switch 2", "target": "PC"})
        b = normalize_project({"owner": "o", "repo": "bravo", "source": "Android", "target": "PS5"})
        c = normalize_project({"owner": "o", "repo": "charlie", "source": "PS3", "target": "Android"})
        assert a and b and c
        items = [a, b, c]

        by_source = [items[i]["repo"] for i in sort_order(items, "source", True)]
        self.assertEqual(by_source, ["bravo", "charlie", "alpha"])

        by_target = [items[i]["repo"] for i in sort_order(items, "target", True)]
        self.assertEqual(by_target, ["charlie", "alpha", "bravo"])

    def test_column_layout_fills_width(self) -> None:
        for avail in (830, 1000, 1200, 1400, 1900):
            w = layout_columns(COL_BASE, COL_MIN, avail)
            self.assertEqual(len(w), 8)
            self.assertTrue(all(a >= m for a, m in zip(w, COL_MIN)))
            if avail >= sum(COL_MIN):
                self.assertEqual(sum(w), avail)

    def test_rename_and_import_export(self) -> None:
        p = normalize_project({"owner": "o", "repo": "repo"})
        assert p is not None
        self.assertEqual(apply_rename(p, "  My  App "), "Renamed to My App.")
        self.assertIsNone(apply_rename(p, "My App"))
        self.assertEqual(apply_rename(p, "repo"), "Name reset to repo.")
        self.assertNotIn("custom_name", p)

        exp = build_export([p], "2026-11-21T10:00:00")
        raw_str = json.dumps(exp)
        self.assertNotIn("token", raw_str)


if __name__ == "__main__":
    unittest.main()
