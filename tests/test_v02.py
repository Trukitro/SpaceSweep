"""v0.2.0: space history, developer projects, long-path deletes, icon encoding."""

import os
import struct
import time
import unittest
import zlib

from spacesweep import devprojects, fsutil, history, imaging, scanner
from spacesweep.jobs import Job

from .test_core import TempCase, write

MB = 1024 * 1024


class HistoryTests(TempCase):
    def test_compare_reports_the_most_specific_folder(self):
        root = self.p("drive")
        history.save_snapshot("scan", root, {"Users": 500 * MB, "Users\\me": 400 * MB, "Users\\me\\cache": 100 * MB,
                                             "Windows": 900 * MB}, 1400 * MB)
        time.sleep(0.01)
        # cache grew by 300 MB (explains Users and Users\me), a new 200 MB folder appeared, Windows shrank
        history.save_snapshot("scan", root, {"Users": 1000 * MB, "Users\\me": 900 * MB, "Users\\me\\cache": 400 * MB,
                                             "Users\\me\\new": 200 * MB, "Windows": 800 * MB}, 1800 * MB)
        key = history.roots()[0]["key"]
        c = history.compare(key)
        grew = {r["path"]: r["delta"] for r in c["grew"]}
        self.assertEqual(grew["Users\\me\\cache"], 300 * MB)
        self.assertEqual(grew["Users\\me\\new"], 200 * MB)
        self.assertNotIn("Users", grew)  # explained by its children... partly: 500 = 300 + 200, no single child >= 80%
        self.assertEqual(c["delta"], 400 * MB)
        self.assertEqual([r["path"] for r in c["shrank"]], ["Windows"])

    def test_single_snapshot_has_nothing_to_compare(self):
        history.save_snapshot("folder", self.p("x"), {"a": 60 * MB}, 60 * MB)
        c = history.compare(history.roots()[0]["key"])
        self.assertIsNone(c["older"])
        self.assertEqual(c["grew"], [])

    def test_snapshots_are_capped_and_small_folders_dropped(self):
        for i in range(history.KEEP_SNAPSHOTS + 3):
            history.save_snapshot("scan", self.p("r"), {"big": 60 * MB, "big\\tiny": MB, "top": 1}, i)
        data = fsutil.load_json(os.path.join("history", f"snap-{history.root_key(self.p('r'))}.json"), None)
        self.assertEqual(len(data["snapshots"]), history.KEEP_SNAPSHOTS)
        self.assertEqual(set(data["snapshots"][-1]["entries"]), {"big", "top"})  # first level always kept

    def test_scan_records_a_snapshot(self):
        write(self.p("tree", "a", "f.bin"), b"x" * 10)
        scanner.scan(Job("t"), self.p("tree"))
        self.assertEqual(history.roots()[0]["root"], self.p("tree"))

    def test_rule_growth_uses_the_emptiest_point(self):
        history.save_rule_sizes("C:\\", [{"id": "nvidia", "size": 5000 * MB, "measured": True}])
        history.save_rule_sizes("C:\\", [{"id": "nvidia", "size": 100 * MB, "measured": True}])  # after a clean-up
        history.save_rule_sizes("C:\\", [{"id": "nvidia", "size": 900 * MB, "measured": True}])
        g = history.rule_growth("C:\\")
        self.assertEqual(g["items"][0]["delta"], 800 * MB)

    def test_free_log_merges_points_within_an_hour(self):
        d = {"root": "Z:\\", "used": 1, "free": 2}
        history.log_free([d])
        history.log_free([dict(d, used=5)])
        self.assertEqual(len(history.free_series("Z:\\")), 1)
        self.assertEqual(history.free_series("Z:\\")[0][1], 5)


class DevProjectTests(TempCase):
    def test_finds_projects_junk_and_activity(self):
        node = self.p("code", "web")
        write(os.path.join(node, "package.json"), b"{}", age_days=200)
        write(os.path.join(node, "src", "index.js"), b"x", age_days=200)
        write(os.path.join(node, "node_modules", "dep", "a.js"), b"y" * 1000)  # fresh, but it is junk: ignored for activity
        py = self.p("code", "tool")
        write(os.path.join(py, "pyproject.toml"), b"", age_days=1)
        write(os.path.join(py, ".venv", "pyvenv.cfg"), b"home=x")
        write(os.path.join(py, ".venv", "Lib", "x.py"), b"z" * 500)
        write(os.path.join(py, "dist", "tool.whl"), b"w" * 300)
        rs = self.p("code", "rs")
        write(os.path.join(rs, "Cargo.toml"), b"", age_days=400)
        write(os.path.join(rs, "target", "debug", "app.exe"), b"t" * 800)
        write(self.p("code", "notes", "target", "keep.txt"), b"not a rust target")  # no Cargo.toml: untouched

        res = devprojects.scan(Job("t"), [self.p("code")], inactive_days=90, min_size=0)
        by = {p["name"]: p for p in res["projects"]}
        self.assertEqual(set(by), {"web", "tool", "rs"})
        self.assertTrue(by["web"]["inactive"])
        self.assertGreaterEqual(by["web"]["idle_days"], 199)
        self.assertEqual(by["web"]["junk"][0]["kind"], "node_modules")
        self.assertFalse(by["tool"]["inactive"])
        kinds = {j["kind"]: j for j in by["tool"]["junk"]}
        self.assertTrue(kinds["dist"]["review"])
        self.assertEqual(kinds["venv"]["size"], 506)
        self.assertEqual(by["rs"]["junk"][0]["regen"], "cargo build")
        self.assertEqual(res["inactive_total"], 1000 + 800)


class LongPathTests(TempCase):
    def test_permanent_delete_of_a_very_deep_tree(self):
        deep = self.p("nm")
        for i in range(30):
            deep = os.path.join(deep, f"folder_{i:02d}_xxxxxxxx")
        os.makedirs(fsutil.long_path(deep))
        with open(fsutil.long_path(os.path.join(deep, "file.js")), "wb") as fh:
            fh.write(b"x")
        self.assertGreater(len(deep), 300)
        res = fsutil.delete_paths([self.p("nm")], permanent=True)
        self.assertTrue(res[0]["ok"], res)
        self.assertFalse(os.path.exists(self.p("nm")))


class ImagingTests(unittest.TestCase):
    def test_png_and_ico_are_well_formed(self):
        data = imaging.png(2, 1, bytes([255, 0, 0, 255, 0, 255, 0, 128]))
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        w, h = struct.unpack(">II", data[16:24])
        self.assertEqual((w, h), (2, 1))
        idat = data[data.index(b"IDAT") + 4:data.index(b"IEND") - 8]
        self.assertEqual(zlib.decompress(idat), b"\x00" + bytes([255, 0, 0, 255, 0, 255, 0, 128]))
        icon = imaging.ico([(16, data), (256, data)])
        self.assertEqual(struct.unpack("<HHH", icon[:6]), (0, 1, 2))
        self.assertEqual(icon[6 + 16], 0)  # 256 px is written as 0


if __name__ == "__main__":
    unittest.main()
