"""v0.8.0: smart Recycle Bin, game recordings, messaging/mail cleanup rules, weekly recycle option."""

import os
import struct
import time
import unittest
from unittest import mock

from spacesweep import automation, cleanup, recordings, recyclebin
from spacesweep.jobs import Job

from .test_core import TempCase, write

EPOCH = 11644473600


def info_v2(path, size, deleted):
    ft = int((deleted + EPOCH) * 10_000_000)
    name = (path + "\0").encode("utf-16-le")
    return struct.pack("<qqqi", 2, size, ft, len(name) // 2) + name


def info_v1(path, size, deleted):
    ft = int((deleted + EPOCH) * 10_000_000)
    return struct.pack("<qqq", 1, size, ft) + path.encode("utf-16-le").ljust(520, b"\0")


class RecycleBinTests(TempCase):
    def make_bin(self):
        b = self.p("$Recycle.Bin", "S-1-5-21-test")
        now = time.time()
        write(os.path.join(b, "$IAAA111.txt"), info_v2(r"C:\Users\me\old.txt", 100, now - 100 * 86400))
        write(os.path.join(b, "$RAAA111.txt"), b"o" * 100)
        write(os.path.join(b, "$IBBB222"), info_v1(r"C:\Users\me\OldFolder", 0, now - 40 * 86400))
        write(os.path.join(b, "$RBBB222", "inner.bin"), b"i" * 300)
        write(os.path.join(b, "$ICCC333.jpg"), info_v2(r"C:\Users\me\recent.jpg", 50, now - 2 * 86400))
        write(os.path.join(b, "$RCCC333.jpg"), b"r" * 50)
        write(os.path.join(b, "desktop.ini"), b"[.ShellClassInfo]")
        return b

    def test_parse_and_summary(self):
        b = self.make_bin()
        s = recyclebin.summary([b])
        self.assertEqual(s["count"], 3)
        self.assertEqual(s["size"], 450)  # folder size measured from its content
        self.assertEqual(s["older_than"]["30"], {"count": 2, "size": 400})
        self.assertEqual(s["older_than"]["90"], {"count": 1, "size": 100})
        names = {i["name"] for i in s["items"]}
        self.assertEqual(names, {"old.txt", "OldFolder", "recent.jpg"})

    def test_empty_older_keeps_recent(self):
        b = self.make_bin()
        res = recyclebin.empty_older_than(30, [b])
        self.assertEqual((res["removed"], res["freed"], res["failed"]), (2, 400, 0))
        left = sorted(os.listdir(b))
        self.assertEqual(left, ["$ICCC333.jpg", "$RCCC333.jpg", "desktop.ini"])


class RecordingsTests(TempCase):
    def test_scan_sources(self):
        cap = self.p("Videos", "Captures")
        write(os.path.join(cap, "Game 2025-01-01.mp4"), b"v" * (6 * 1024 * 1024), age_days=200)
        write(os.path.join(cap, "tiny.mp4"), b"v" * 1000)  # under the size floor for videos
        write(os.path.join(cap, "shot.png"), b"p" * 2000)   # screenshots count at any size
        write(os.path.join(cap, "notes.txt"), b"x")
        with mock.patch.object(recordings, "sources", return_value=[("Xbox Game Bar", cap, recordings.VIDEO | recordings.IMAGE)]):
            res = recordings.scan(Job("t"))
        src = res["sources"][0]
        self.assertEqual(src["count"], 2)
        self.assertEqual(src["older_90"], 6 * 1024 * 1024)
        self.assertEqual(src["files"][0]["age_days"] >= 199, True)

    def test_obs_paths_from_profiles(self):
        appdata = self.p("roaming")
        write(os.path.join(appdata, "obs-studio", "basic", "profiles", "Main", "basic.ini"),
              "[SimpleOutput]\nFilePath=D:/Rec\n[AdvOut]\nRecFilePath=E:/OBS\n")
        with mock.patch.dict(os.environ, {"APPDATA": appdata}):
            self.assertEqual(sorted(recordings._obs_paths()), ["D:\\Rec", "E:\\OBS"])


class RecordingSourceTests(TempCase):
    def test_temp_root_is_never_a_capture_folder_and_paths_are_normalised(self):
        temp = self.p("tmp")
        nv = self.p("Videos", "NVIDIA")
        os.makedirs(temp)
        os.makedirs(nv)
        with mock.patch.dict(os.environ, {"TEMP": temp, "TMP": temp}), \
                mock.patch.object(recordings, "_nvidia_paths", return_value=[temp, nv.replace("\\", "\\\\")]), \
                mock.patch.object(recordings, "_obs_paths", return_value=[]), \
                mock.patch("spacesweep.inventory._steam_root", return_value=None), \
                mock.patch.object(recordings.winapi, "known_folder", return_value=self.p("Videos")):
            paths = [p for _, p, _ in recordings.sources()]
        self.assertEqual(paths, [nv])


class RuleAndAutomationTests(TempCase):
    def test_new_rules_present_and_safe(self):
        ids = {r["id"]: r for r in cleanup.RULES}
        self.assertEqual(ids["chat_cache"]["group"], "safe")
        self.assertEqual(ids["thunderbird_index"]["group"], "review")
        self.assertEqual(ids["chat_media"]["mode"], "info")  # user media is never deleted by SpaceSweep

    def test_weekly_recycle_days_setting(self):
        s = automation.save_settings({"weekly_clean": {"recycle_days": "45"}}, register=False)["settings"]
        self.assertEqual(s["weekly_clean"]["recycle_days"], 45)
        s = automation.save_settings({"weekly_clean": {"recycle_days": -3}}, register=False)["settings"]
        self.assertEqual(s["weekly_clean"]["recycle_days"], 0)


if __name__ == "__main__":
    unittest.main()
