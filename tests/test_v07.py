"""v0.7.0: NTFS compression, the 'free N GB' planner, update check and changelog."""

import io
import json
import os
import unittest
from unittest import mock

from spacesweep import __version__, compress, planner, updates, winapi
from spacesweep.jobs import Job

from .test_core import TempCase, write

GB = 1024 ** 3


@unittest.skipUnless(winapi.IS_WINDOWS, "NTFS compression is Windows-only")
class CompressTests(TempCase):
    def test_status_compress_and_revert_keep_contents(self):
        folder = self.p("game")
        text = (b"SpaceSweep compressible game data " * 40000)
        write(os.path.join(folder, "data", "level1.bin"), text)
        write(os.path.join(folder, "movie.mp4"), os.urandom(200_000))
        st = compress.status(Job("t"), folder)
        self.assertEqual(st["files"], 2)
        self.assertGreater(st["estimate_saving"], len(text) // 2)  # text compresses a lot, the mp4 is skipped
        res = compress.compress(Job("t"), folder, "XPRESS8K")
        self.assertGreater(res["saved"], len(text) // 2, res["output"])
        with open(os.path.join(folder, "data", "level1.bin"), "rb") as fh:
            self.assertEqual(fh.read(), text)  # programs still read it transparently
        back = compress.decompress(Job("t"), folder)
        self.assertGreaterEqual(back["after"], len(text))

    def test_rejects_unknown_algorithm(self):
        with self.assertRaises(ValueError):
            compress.compress(Job("t"), self.tmp, "ZIP")


class PlannerTests(TempCase):
    def test_plan_orders_by_risk_and_reaches_target(self):
        scan = {"items": [
            {"id": "nvidia_shader", "group": "safe", "exists": True, "measured": True, "size": 9 * GB, "admin": False},
            {"id": "update_cache", "group": "safe", "exists": True, "measured": True, "size": 4 * GB, "admin": True},
            {"id": "recycle_bin", "group": "review", "exists": True, "measured": True, "size": 2 * GB, "admin": False},
        ]}
        games = {"games": [{"path": "C:\\Games\\Old", "idle_days": 400, "size": 100 * GB},
                           {"path": "C:\\Games\\New", "idle_days": 3, "size": 80 * GB}]}
        with mock.patch.object(planner.cleanup, "scan", return_value=scan), \
                mock.patch.object(planner.devprojects, "default_roots", return_value=[]), \
                mock.patch.object(planner.inventory, "lmstudio_runtimes", return_value=[]), \
                mock.patch.object(planner.inventory, "vscode_leftovers", return_value=[]), \
                mock.patch.object(planner.inventory, "jetbrains_leftovers", return_value=[]), \
                mock.patch.object(planner, "compress_candidates", return_value=[{"path": "C:\\Games\\Old", "size": 100 * GB}]), \
                mock.patch.object(planner.winapi, "list_drives", return_value=[]), \
                mock.patch.object(planner.winapi, "is_admin", return_value=False), \
                mock.patch.object(planner.inventory, "games", return_value=games):
            plan = planner.build(Job("t"), "C:\\", 20 * GB)
        ids = [s["id"] for s in plan["steps"]]
        self.assertEqual(ids, ["cleanup_safe", "cleanup_admin", "recycle_bin", "compress", "games"])
        self.assertEqual([s["risk"] for s in plan["steps"]], sorted(s["risk"] for s in plan["steps"]))
        self.assertEqual(plan["steps"][-1]["size"], 100 * GB)  # only the game idle for 180+ days
        first = next(i for i, s in enumerate(plan["steps"]) if s["reaches"])
        self.assertEqual(ids[first], "compress")  # 9 + 4 + 2 = 15 GB < 20, compression gets there
        self.assertTrue(plan["reachable"])


class UpdateTests(TempCase):
    def fake(self, tag):
        body = json.dumps({"tag_name": tag, "html_url": "https://github.com/Trukitro/SpaceSweep/releases/tag/" + tag,
                           "body": "notes", "assets": [{"name": "SpaceSweepSetup.exe", "browser_download_url": "https://x/setup"}]})
        calls = []

        def opener(req, timeout):
            calls.append(req.full_url)
            return io.BytesIO(body.encode())
        return opener, calls

    def test_newer_release_and_daily_cache(self):
        opener, calls = self.fake("v99.0.0")
        r = updates.check(opener=opener)
        self.assertTrue(r["newer"])
        self.assertEqual((r["latest"], r["setup"]), ("99.0.0", "https://x/setup"))
        updates.check(opener=opener)
        self.assertEqual(len(calls), 1)  # second call served from the 24 h cache

    def test_same_version_is_not_newer_and_can_be_disabled(self):
        opener, calls = self.fake("v" + __version__)
        self.assertFalse(updates.check(force=True, opener=opener)["newer"])
        from spacesweep import fsutil
        s = fsutil.load_json("settings.json", {})
        s["check_updates"] = False
        fsutil.save_json("settings.json", s)
        self.assertFalse(updates.check(opener=opener)["enabled"])

    def test_versions_and_whats_new(self):
        self.assertGreater(updates.parse_version("v1.2.10"), updates.parse_version("1.2.9"))
        self.assertIsNone(updates.whats_new())  # first run: nothing to show
        from spacesweep import fsutil
        s = fsutil.load_json("settings.json", {})
        s["last_seen_version"] = "0.1.0"
        fsutil.save_json("settings.json", s)
        self.assertEqual(updates.whats_new(), {"from": "0.1.0", "to": __version__})
        self.assertIsNone(updates.whats_new())  # shown once

    def test_changelog_is_bundled_and_mentions_this_version(self):
        text = updates.changelog()
        self.assertIn("## " + __version__, text)


if __name__ == "__main__":
    unittest.main()
