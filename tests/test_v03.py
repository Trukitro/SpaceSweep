"""v0.3.0: automation (settings, task XML, alerts, Downloads rules)."""

import collections
import os
import unittest
from unittest import mock
from xml.dom import minidom

from spacesweep import automation, fsutil, winapi

from .test_core import TempCase, write

Usage = collections.namedtuple("Usage", "total used free")
GB = 1024 ** 3


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, title, body):
        self.calls.append((title, body))
        return True


class SettingsTests(TempCase):
    def test_defaults_merge_and_validation(self):
        res = automation.save_settings({"alert": {"enabled": 1, "percent": 99, "time": "7:5"},
                                        "weekly_clean": {"day": "XYZ"}, "downloads": {"installer_days": -3, "bogus": 1}},
                                       register=False)
        s = res["settings"]
        self.assertEqual(s["alert"], {"enabled": True, "percent": 50, "time": "07:05"})
        self.assertEqual(s["weekly_clean"]["day"], "SUN")
        self.assertEqual(s["downloads"]["installer_days"], 1)
        self.assertNotIn("bogus", s["downloads"])
        self.assertEqual(automation.get_settings(), s)  # persisted

    def test_task_xml_is_valid_and_points_at_this_install(self):
        s = automation.get_settings()
        s["weekly_clean"].update(day="WED", time="18:30")
        for mode in ("check", "clean"):
            xml = automation.task_xml(mode, s)
            doc = minidom.parseString(xml.replace('encoding="UTF-16"', 'encoding="UTF-8"').encode())
            args = doc.getElementsByTagName("Arguments")[0].firstChild.data
            self.assertTrue(args.endswith(f"--{'check' if mode == 'check' else 'clean'}") or args.endswith("--clean"))
            self.assertEqual(doc.getElementsByTagName("RunLevel")[0].firstChild.data, "LeastPrivilege")
        clean = automation.task_xml("clean", s)
        self.assertIn("<Wednesday />", clean)
        self.assertIn("T18:30:00", clean)
        launcher = os.path.join(fsutil.app_data_dir(), "task_launcher.pyw")
        with open(launcher, encoding="utf-8") as fh:
            self.assertIn("from spacesweep.__main__ import main", fh.read())


class CheckTests(TempCase):
    def test_low_space_alert_once_a_day(self):
        automation.save_settings({"alert": {"enabled": True, "percent": 10}}, register=False)
        rec = Recorder()
        low = Usage(100 * GB, 95 * GB, 5 * GB)
        r1 = automation.run_check(now=1_000_000, usage=low, notifier=rec)
        r2 = automation.run_check(now=1_000_000 + 3600, usage=low, notifier=rec)
        r3 = automation.run_check(now=1_000_000 + 21 * 3600, usage=low, notifier=rec)
        self.assertEqual((r1["alert"], r2["alert"], r3["alert"] is not None), (5.0, None, True))
        self.assertEqual(len(rec.calls), 2)
        self.assertEqual([e["kind"] for e in automation.read_log()], ["alert", "alert"])

    def test_no_alert_when_enough_space_or_disabled(self):
        rec = Recorder()
        automation.run_check(usage=Usage(100 * GB, 10 * GB, 90 * GB), notifier=rec)
        automation.save_settings({"alert": {"enabled": True, "percent": 10}}, register=False)
        automation.run_check(usage=Usage(100 * GB, 50 * GB, 50 * GB), notifier=rec)
        self.assertEqual(rec.calls, [])


class DownloadRulesTests(TempCase):
    def test_rules_pick_and_apply(self):
        dl = self.p("Downloads")
        data = os.urandom(3000)
        write(os.path.join(dl, "app.exe"), data, age_days=40)
        write(os.path.join(dl, "app (1).exe"), data, age_days=40)
        write(os.path.join(dl, "new-setup.msi"), b"m", age_days=3)
        write(os.path.join(dl, "film.mkv.crdownload"), b"p", age_days=10)
        write(os.path.join(dl, "doc.pdf"), b"%PDF")
        rules = dict(automation.DEFAULTS["downloads"], enabled=True, organize=True)
        real = fsutil.delete_paths
        rec = Recorder()
        # permanent delete in tests so nothing lands in the real Recycle Bin
        with mock.patch.object(automation.fsutil, "delete_paths", lambda paths, permanent=False: real(paths, True)):
            res = automation.run_downloads_rules(rules, folder=dl, notifier=rec)
        # the copy goes as a duplicate, the 40-day-old original as an old installer; the 3-day-old msi stays
        self.assertEqual(sorted(res["files"]), ["app (1).exe", "app.exe", "film.mkv.crdownload"])
        self.assertEqual(res["recycled"], 3)
        self.assertTrue(os.path.isfile(os.path.join(dl, "Instaladores", "new-setup.msi")))
        self.assertTrue(os.path.isfile(os.path.join(dl, "Documentos", "doc.pdf")))
        self.assertEqual(len(rec.calls), 1)
        self.assertEqual(automation.read_log()[-1]["kind"], "downloads")


@unittest.skipUnless(winapi.IS_WINDOWS and os.environ.get("SPACESWEEP_TEST_SCHTASKS") == "1",
                     "creates a real scheduled task; set SPACESWEEP_TEST_SCHTASKS=1")
class SchedulerRoundTrip(TempCase):
    def test_register_query_delete(self):
        name = "\\SpaceSweep - selftest"
        s = automation.get_settings()
        ok, msg = automation.register_task("check", s, name=name)
        try:
            self.assertTrue(ok, msg)
            self.assertIsNotNone(automation.task_info(name))
        finally:
            automation.delete_task(name)
        self.assertIsNone(automation.task_info(name))


if __name__ == "__main__":
    unittest.main()
