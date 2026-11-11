"""v0.5.0: duplicates against a backup, moving folders with a junction, DISM output parsing."""

import os
import shutil
import tempfile
import unittest

from spacesweep import duplicates, fsutil, mover, winmaint
from spacesweep.jobs import Job

from .test_core import TempCase, write

SAMPLE_DISM = """
Deployment Image Servicing and Management tool
Version: 10.0.22621.2792

Image Version: 10.0.22631.4460

[==========================100.0%==========================]

Component Store (WinSxS) information:

Windows Explorer Reported Size of Component Store : 9.85 GB

Actual Size of Component Store : 8.92 GB

    Shared with Windows : 5.58 GB
    Backups and Disabled Features : 3.21 GB
    Cache and Temporary Data :  134.29 MB

Date of Last Cleanup : 2026-10-01 10:15:22

Number of Reclaimable Packages : 3
Component Store Cleanup Recommended : Yes

The operation completed successfully.
"""


class BackupDuplicateTests(TempCase):
    def test_only_files_already_in_the_backup(self):
        a, b, c = os.urandom(5000), os.urandom(6000), os.urandom(7000)
        write(self.p("C", "photo.jpg"), a)            # backed up -> reported, deletable
        write(self.p("C", "copy of photo.jpg"), a)    # also backed up
        write(self.p("C", "only-here.bin"), b)        # no backup copy -> not reported
        write(self.p("C", "x1.bin"), c)               # duplicated only inside C: -> not reported in backup mode
        write(self.p("C", "x2.bin"), c)
        write(self.p("J", "backup", "photo.jpg"), a)
        res = duplicates.find(Job("t"), [self.p("C")], min_size=1, reference=[self.p("J")])
        self.assertEqual(res["total_groups"], 1)
        g = res["groups"][0]
        self.assertEqual([f["ref"] for f in g["files"]], [True, False, False])  # reference first
        self.assertEqual(g["wasted"], 2 * 5000)

    def test_folder_in_both_lists_counts_as_backup(self):
        data = os.urandom(3000)
        write(self.p("B", "a.bin"), data)
        write(self.p("B", "b.bin"), data)
        res = duplicates.find(Job("t"), [self.p("B")], min_size=1, reference=[self.p("B")])
        self.assertEqual(res["total_groups"], 0)  # nothing outside the backup


class MoverCheckTests(TempCase):
    def test_refusals(self):
        write(self.p("src", "f.bin"), b"x")
        with self.assertRaises(ValueError):
            mover.check(self.p("src"), self.p("dest"))  # same drive
        with self.assertRaises(ValueError):
            mover.check(self.p("missing"), "Z:\\")
        with self.assertRaises(ValueError):
            mover.check(os.path.expanduser("~"), "Z:\\")  # protected profile root
        with self.assertRaises(ValueError):
            mover.check(os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Common Files"), "Z:\\")


@unittest.skipUnless(os.environ.get("SPACESWEEP_TEST_MOVE_DRIVE"), "set SPACESWEEP_TEST_MOVE_DRIVE=J:\\ to test a real cross-drive move")
class MoverRoundTrip(TempCase):
    def test_move_then_restore(self):
        drive = os.environ["SPACESWEEP_TEST_MOVE_DRIVE"]
        dest = tempfile.mkdtemp(prefix="spacesweep-movetest-", dir=drive)
        try:
            src = self.p("models")
            write(os.path.join(src, "a.gguf"), b"a" * 4096)
            write(os.path.join(src, "sub", "b.bin"), b"b" * 100)
            res = mover.move(Job("t"), src, dest)
            self.assertTrue(fsutil.is_link_path(src))
            with open(os.path.join(src, "sub", "b.bin"), "rb") as fh:  # still readable through the junction
                self.assertEqual(fh.read(), b"b" * 100)
            self.assertTrue(os.path.isfile(os.path.join(res["target"], "a.gguf")))
            self.assertFalse(os.path.exists(src + mover.OLD_SUFFIX))
            self.assertEqual(len(mover.list_moves()), 1)
            self.assertTrue(mover.list_moves()[0]["linked"])

            mover.restore(Job("t"), src)
            self.assertFalse(fsutil.is_link_path(src))
            self.assertEqual(fsutil.dir_size(src)[:2], (4196, 2))
            self.assertFalse(os.path.exists(res["target"]))
            self.assertEqual(mover.list_moves(), [])
        finally:
            shutil.rmtree(dest, ignore_errors=True)

    def test_files_in_use_abort_without_changes(self):
        drive = os.environ["SPACESWEEP_TEST_MOVE_DRIVE"]
        dest = tempfile.mkdtemp(prefix="spacesweep-movetest-", dir=drive)
        src = self.p("busy")
        path = write(os.path.join(src, "open.bin"), b"z" * 10)
        try:
            with open(path, "rb"):
                with self.assertRaises(ValueError):
                    mover.move(Job("t"), src, dest)
            self.assertFalse(fsutil.is_link_path(src))
            self.assertEqual(os.listdir(dest), [])
        finally:
            shutil.rmtree(dest, ignore_errors=True)


class DismParseTests(unittest.TestCase):
    def test_parse(self):
        d = winmaint.parse_analysis(SAMPLE_DISM)
        self.assertTrue(d["recommended"])
        self.assertEqual(d["Actual Size of Component Store"], "8.92 GB")
        self.assertEqual(d["Number of Reclaimable Packages"], "3")
        self.assertNotIn("Version", d)
        self.assertFalse(winmaint.parse_analysis("Component Store Cleanup Recommended : No")["recommended"])


if __name__ == "__main__":
    unittest.main()
