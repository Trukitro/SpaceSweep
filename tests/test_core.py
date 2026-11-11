"""Tests for everything that deletes or moves files. All of them work in temp folders."""

import json
import os
import shutil
import struct
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from spacesweep import analyzer, cleanup, duplicates, fsutil, organizer, scanner, winapi
from spacesweep.jobs import Job


def write(path, data=b"x", age_days=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode())
    if age_days:
        t = time.time() - age_days * 86400
        os.utime(path, (t, t))
    return path


class TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="spacesweep-test-")
        self._old_local = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = os.path.join(self.tmp, "_appdata")  # undo logs/settings stay in the sandbox

    def tearDown(self):
        if self._old_local is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._old_local
        shutil.rmtree(self.tmp, ignore_errors=True)

    def p(self, *parts):
        return os.path.join(self.tmp, *parts)


class FsutilTests(TempCase):
    def test_delete_contents_respects_age_and_keeps_root(self):
        write(self.p("cache", "old.bin"), b"a" * 100, age_days=5)
        write(self.p("cache", "sub", "old2.bin"), b"b" * 50, age_days=5)
        write(self.p("cache", "new.bin"), b"c" * 10)
        freed, deleted, skipped = fsutil.delete_contents(self.p("cache"), older_than_days=1)
        self.assertEqual((freed, deleted, skipped), (150, 2, 0))
        self.assertTrue(os.path.isdir(self.p("cache")))
        self.assertTrue(os.path.exists(self.p("cache", "new.bin")))
        self.assertFalse(os.path.exists(self.p("cache", "sub")))  # emptied subfolder removed

    def test_delete_contents_clears_readonly(self):
        f = write(self.p("c", "ro.txt"), b"z")
        os.chmod(f, 0o444)
        self.assertEqual(fsutil.delete_contents(self.p("c"))[1], 1)

    def test_check_deletable_refuses_dangerous_targets(self):
        for bad in ("C:\\", os.environ.get("SystemRoot", r"C:\Windows"), os.path.expanduser("~"),
                    winapi.known_folder("documents"), os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "x.dll")):
            with self.assertRaises(ValueError, msg=bad):
                fsutil.check_deletable(bad)
        fsutil.check_deletable(self.p("anything.txt"))  # ordinary paths are fine

    def test_delete_paths_permanent(self):
        a = write(self.p("a.txt"), b"1234")
        d = write(self.p("dir", "b.txt"), b"56")
        res = fsutil.delete_paths([a, os.path.dirname(d), self.p("missing.txt")], permanent=True)
        self.assertEqual([r["ok"] for r in res], [True, True, False])
        self.assertEqual(res[0]["size"], 4)
        self.assertFalse(os.path.exists(a) or os.path.exists(os.path.dirname(d)))

    @unittest.skipUnless(winapi.IS_WINDOWS and not os.environ.get("GITHUB_ACTIONS"),
                         "Recycle Bin needs an interactive Windows session")
    def test_send_to_recycle_bin(self):
        f = write(self.p("recycle-me.txt"), b"spacesweep test file, safe to delete")
        res = fsutil.delete_paths([f], permanent=False)
        self.assertTrue(res[0]["ok"], res)
        self.assertFalse(os.path.exists(f))
        # take our test file back out of the real Recycle Bin
        from spacesweep import recyclebin
        mine = [i for i in recyclebin.items() if os.path.normcase(i["original"]) == os.path.normcase(f)]
        self.assertEqual(len(mine), 1)
        os.remove(mine[0]["data"])
        os.remove(mine[0]["info"])

    def test_unique_target(self):
        write(self.p("f.txt"))
        write(self.p("f (2).txt"))
        self.assertEqual(fsutil.unique_target(self.p("f.txt")), self.p("f (3).txt"))


class DuplicateTests(TempCase):
    def test_exact_duplicates_only(self):
        big = os.urandom(300_000)
        write(self.p("a", "one.bin"), big)
        write(self.p("b", "copy.bin"), big)
        write(self.p("b", "copy2.bin"), big)
        write(self.p("a", "same-size-different.bin"), big[:-1] + bytes([big[-1] ^ 1]))  # differs in the last byte
        write(self.p("a", "small.bin"), b"tiny")
        write(self.p("b", "small.bin"), b"tiny")
        res = duplicates.find(Job("t"), [self.p("a"), self.p("b")], min_size=1000)
        self.assertEqual(res["total_groups"], 1)
        g = res["groups"][0]
        self.assertEqual(g["count"], 3)
        self.assertEqual(res["wasted"], 2 * 300_000)

    def test_overlapping_folders_not_double_counted(self):
        data = os.urandom(5000)
        write(self.p("x", "a.bin"), data)
        write(self.p("x", "y", "b.bin"), data)
        res = duplicates.find(Job("t"), [self.p("x"), self.p("x", "y")], min_size=1)
        self.assertEqual(res["groups"][0]["count"], 2)

    @unittest.skipUnless(hasattr(os, "link"), "hard links unsupported")
    def test_hard_links_are_not_duplicates(self):
        f = write(self.p("h", "a.bin"), os.urandom(5000))
        os.link(f, self.p("h", "b.bin"))
        res = duplicates.find(Job("t"), [self.p("h")], min_size=1)
        self.assertEqual(res["total_groups"], 0)


def tiny_jpeg_with_exif(date_str):
    """Smallest JPEG header with an EXIF DateTimeOriginal tag (enough for exif_date)."""
    date = date_str.encode() + b"\0"
    # little-endian TIFF: header(8) + IFD0 with 1 entry -> ExifIFD with 1 entry -> date string
    ifd0_off, exif_off = 8, 8 + 2 + 12 + 4
    date_off = exif_off + 2 + 12 + 4
    tiff = b"II*\0" + struct.pack("<I", ifd0_off)
    tiff += struct.pack("<H", 1) + struct.pack("<HHII", 0x8769, 4, 1, exif_off) + struct.pack("<I", 0)
    tiff += struct.pack("<H", 1) + struct.pack("<HHII", 0x9003, 2, len(date), date_off) + struct.pack("<I", 0)
    tiff += date
    app1 = b"Exif\0\0" + tiff
    return b"\xff\xd8" + b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1 + b"\xff\xd9"


class OrganizerTests(TempCase):
    def test_downloads_suggestions_and_round_trip(self):
        dl = self.p("Downloads")
        setup = os.urandom(2000)
        write(os.path.join(dl, "setup.exe"), setup, age_days=30)
        write(os.path.join(dl, "setup (1).exe"), setup, age_days=2)
        write(os.path.join(dl, "movie.mp4.crdownload"), b"partial", age_days=3)
        write(os.path.join(dl, "photos.zip"), b"zipdata")
        os.makedirs(os.path.join(dl, "photos"))
        write(os.path.join(dl, "report.pdf"), b"%PDF")
        res = organizer.analyze_downloads(Job("t"), dl, "es")
        reasons = {s["name"]: s["reason"] for s in res["suggestions"]}
        self.assertEqual(reasons["setup (1).exe"], "duplicate")
        self.assertEqual(reasons["movie.mp4.crdownload"], "partial")
        self.assertEqual(reasons["photos.zip"], "extracted")
        self.assertEqual(reasons["setup.exe"], "old_installer")
        self.assertNotIn("report.pdf", reasons)
        self.assertNotIn("movie.mp4.crdownload", [m["name"] for m in res["moves"]])  # never move partial downloads

        out = organizer.apply_plan(Job("t"), res["plan_id"])
        self.assertEqual(out["moved"], 4)
        self.assertTrue(os.path.isfile(os.path.join(dl, "Documentos", "report.pdf")))
        self.assertTrue(os.path.isfile(os.path.join(dl, "Instaladores", "setup.exe")))
        self.assertTrue(os.path.isdir(os.path.join(dl, "photos")))  # existing folders untouched

        info = organizer.last_undo("downloads")
        self.assertEqual(info["files"], 4)
        back = organizer.undo(Job("t"), info["name"])
        self.assertEqual(back["restored"], 4)
        self.assertTrue(os.path.isfile(os.path.join(dl, "report.pdf")))
        self.assertFalse(os.path.exists(os.path.join(dl, "Documentos")))  # created folders cleaned up
        self.assertIsNone(organizer.last_undo("downloads"))

    def test_apply_skips_files_deleted_after_analysis(self):
        dl = self.p("D")
        write(os.path.join(dl, "a.pdf"))
        write(os.path.join(dl, "b.pdf"))
        res = organizer.analyze_downloads(Job("t"), dl, "en")
        os.remove(os.path.join(dl, "a.pdf"))
        out = organizer.apply_plan(Job("t"), res["plan_id"])
        self.assertEqual((out["moved"], out["failed"]), (1, []))

    def test_exif_date_and_media_plan(self):
        pics = self.p("Pictures")
        write(os.path.join(pics, "IMG_1.jpg"), tiny_jpeg_with_exif("2019:07:04 10:20:30"))
        write(os.path.join(pics, "clip.mp4"), b"video", age_days=0)
        write(os.path.join(pics, "notes.txt"), b"not media")
        self.assertEqual(organizer.exif_date(os.path.join(pics, "IMG_1.jpg")).year, 2019)
        plan = organizer.plan_media_by_date(Job("t"), pics)
        self.assertEqual(plan["files"], 2)
        self.assertEqual(plan["exif"], 1)
        organizer.apply_plan(Job("t"), plan["plan_id"])
        self.assertTrue(os.path.isfile(os.path.join(pics, "2019", "2019-07", "IMG_1.jpg")))
        self.assertTrue(os.path.isfile(os.path.join(pics, "notes.txt")))

    def test_exif_date_on_non_jpeg(self):
        self.assertIsNone(organizer.exif_date(write(self.p("x.jpg"), b"not a jpeg")))


class AnalyzerTests(TempCase):
    def test_findings(self):
        root = self.p("Docs")
        write(os.path.join(root, "web", "node_modules", "lib", "index.js"), b"a" * 1000)
        write(os.path.join(root, "py", ".venv", "pyvenv.cfg"), b"home = x")
        write(os.path.join(root, "py", ".venv", "Lib", "big.py"), b"b" * 500)
        write(os.path.join(root, "rs", "Cargo.toml"), b"[package]")
        write(os.path.join(root, "rs", "target", "debug", "app.exe"), b"c" * 800)
        write(os.path.join(root, "db", "backup", "db.bak"), os.urandom(2 * 1024 * 1024))
        write(os.path.join(root, "db", "backup.zip"), b"zip")
        write(os.path.join(root, "~$report.docx"), b"lock")
        res = analyzer.analyze(Job("t"), root)
        by_reason = {f["reason"]: f for f in res["findings"]}
        self.assertEqual(by_reason["node_modules"]["size"], 1000)
        self.assertIn("venv", by_reason)
        self.assertIn("build_cache", by_reason)
        self.assertEqual(by_reason["backup_zipped"]["keep"], "backup.zip")
        self.assertIn("office_lock", by_reason)
        self.assertEqual(res["total"], sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(root) for f in fs))


class ScannerTests(TempCase):
    def test_sizes_and_drilldown(self):
        write(self.p("r", "a", "1.bin"), b"1" * 100)
        write(self.p("r", "a", "deep", "2.bin"), b"2" * 50)
        write(self.p("r", "b", "3.txt"), b"3" * 10)
        write(self.p("r", "top.log"), b"4" * 5)
        s = scanner.scan(Job("t"), self.p("r"))
        self.assertEqual((s["total"], s["files"]), (165, 4))
        root = scanner.children(s["scan_id"], "")
        self.assertEqual([(d["name"], d["size"]) for d in root["dirs"]], [("a", 150), ("b", 10)])
        self.assertEqual([f["name"] for f in root["files"]], ["top.log"])
        self.assertEqual(scanner.children(s["scan_id"], "a")["dirs"][0]["size"], 50)
        self.assertEqual(s["largest"][0]["size"], 100)


class CleanupRuleTests(unittest.TestCase):
    def test_rules_are_complete_and_never_target_protected_roots(self):
        protected = fsutil.protected_paths()
        ids = set()
        for rule in cleanup.RULES:
            self.assertNotIn(rule["id"], ids)
            ids.add(rule["id"])
            self.assertIn(rule["group"], {"safe", "review", "space", "system", "never"})
            for key in ("name", "what", "effect"):
                self.assertTrue(rule[key]["es"] and rule[key]["en"], (rule["id"], key))
            if rule["group"] in ("safe", "review") and rule.get("mode", "contents") == "contents":
                for p in cleanup._resolve(rule):
                    norm = os.path.normcase(os.path.abspath(p)).rstrip("\\/")
                    self.assertNotIn(norm, protected, rule["id"])
                    self.assertGreater(len(norm), 3, rule["id"])

    def test_clean_ignores_info_and_unknown_rules(self):
        rep = cleanup.clean(Job("t"), ["win_installer", "winsxs", "pagefile", "does_not_exist"], "C:\\")
        self.assertEqual(rep["items"], [])


class ServerTests(unittest.TestCase):
    def test_token_and_host_are_required(self):
        from spacesweep import server
        from spacesweep.api import Api
        from http.server import ThreadingHTTPServer
        ui = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "spacesweep", "ui")
        server.UI_DIR = ui
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
        port = httpd.server_address[1]
        httpd.RequestHandlerClass = server._handler(Api(), "secret-token", port)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{port}"
            page = urllib.request.urlopen(url + "/").read()
            self.assertIn(b"secret-token", page)

            def post(token):
                req = urllib.request.Request(url + "/api/drives", data=b"[]", method="POST",
                                             headers={"X-SS-Token": token, "Content-Type": "application/json"})
                return urllib.request.urlopen(req)

            with self.assertRaises(urllib.error.HTTPError) as ctx:
                post("wrong")
            self.assertEqual(ctx.exception.code, 403)
            self.assertTrue(json.loads(post("secret-token").read())["ok"])
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(url + "/../spacesweep/api.py")
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
