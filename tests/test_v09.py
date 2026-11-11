"""v0.9.0: duplicates -> hard links, Explorer right-click entry, --open startup path."""

import os
import unittest
from unittest import mock

from spacesweep import duplicates, shellmenu, winapi
from spacesweep.api import Api
from spacesweep.jobs import Job

from .test_core import TempCase, write

TEST_ROOT = r"Software\SpaceSweepTest"


class HardlinkTests(TempCase):
    def test_replace_duplicate_with_hard_link(self):
        data = os.urandom(50_000)
        keep = write(self.p("a", "setup.exe"), data)
        dup = write(self.p("b", "setup (1).exe"), data)
        res = duplicates.hardlink(Job("t"), [(dup, keep)])
        self.assertEqual((res["ok"], res["freed"]), (1, 50_000), res)
        a, b = os.stat(keep), os.stat(dup)
        self.assertEqual((a.st_ino, a.st_dev), (b.st_ino, b.st_dev))  # one file, two names
        self.assertEqual(a.st_nlink, 2)
        with open(dup, "rb") as fh:
            self.assertEqual(fh.read(), data)
        again = duplicates.hardlink(Job("t"), [(dup, keep)])
        self.assertEqual(again["ok"], 0)  # already linked: nothing to do

    def test_refuses_when_content_differs(self):
        keep = write(self.p("k.bin"), b"a" * 1000)
        dup = write(self.p("d.bin"), b"b" * 1000)
        res = duplicates.hardlink(Job("t"), [(dup, keep)])
        self.assertEqual(res["ok"], 0)
        with open(dup, "rb") as fh:
            self.assertEqual(fh.read(), b"b" * 1000)  # untouched
        self.assertFalse(os.path.exists(dup + ".spacesweep-link"))


@unittest.skipUnless(winapi.IS_WINDOWS, "registry")
class ShellMenuTests(TempCase):
    def tearDown(self):
        import winreg

        def wipe(path):
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
                    subs = [winreg.EnumKey(k, i) for i in range(winreg.QueryInfoKey(k)[0])]
            except OSError:
                return
            for s in subs:
                wipe(path + "\\" + s)
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        wipe(TEST_ROOT)
        super().tearDown()

    def test_install_and_uninstall_in_a_test_key(self):
        keys = {TEST_ROOT + r"\Directory\shell\SpaceSweep": "%1", TEST_ROOT + r"\Background\shell\SpaceSweep": "%V"}
        with mock.patch.object(shellmenu, "KEYS", keys):
            st = shellmenu.install("es")
            self.assertTrue(st["installed"])
            self.assertTrue(st["command"].endswith('--open "%1"'), st["command"])
            self.assertFalse(shellmenu.uninstall()["installed"])


class StartupPathTests(unittest.TestCase):
    def test_consumed_once(self):
        api = Api()
        api._startup_path = r"C:\Games"
        self.assertEqual(api.startup_path(), r"C:\Games")
        self.assertIsNone(api.startup_path())


if __name__ == "__main__":
    unittest.main()
