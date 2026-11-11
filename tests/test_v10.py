"""v1.0.0: exportable report."""

import csv
import os
import time
import unittest

from spacesweep import report

from .test_core import TempCase

SAMPLE = {
    "time": time.time(), "version": "1.0.0",
    "drives": [{"letter": "C", "label": "System", "root": "C:\\", "free": 50, "used": 150, "total": 200}],
    "cleanup": {"drive": "C:\\", "items": [
        {"id": "user_temp", "group": "safe", "measured": True, "size": 2048,
         "name": {"es": "Temporales <tuyos>", "en": "Your temp files"}, "what": {"es": "x", "en": "x"},
         "effect": {"es": "Nada", "en": "Nothing"}, "paths": [{"path": os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp")}]}]},
    "growth": {"root": "C:\\", "older": {"time": time.time() - 86400}, "newer": {"time": time.time()},
               "grew": [{"full": os.path.join(os.path.expanduser("~"), "Videos"), "before": 1, "after": 3, "delta": 2}]},
    "caches": {"items": []}, "auto": [],
}


class ReportTests(TempCase):
    def test_html_is_escaped_and_hides_user_name(self):
        page = report.to_html(SAMPLE, "es")
        self.assertIn("Temporales &lt;tuyos&gt;", page)
        self.assertNotIn(os.path.expanduser("~"), page)
        self.assertIn("~\\Videos", page)

    def test_csv_has_bom_and_rows(self):
        path = self.p("r.csv")
        report.to_csv(SAMPLE, path, "en")
        with open(path, "rb") as fh:
            self.assertTrue(fh.read(3) == b"\xef\xbb\xbf")
        with open(path, encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(rows[0], ["section", "name", "group", "bytes", "path"])
        self.assertIn(["cleanup", "Your temp files", "Safe", "2048", "~\\AppData\\Local\\Temp"], rows)
        self.assertEqual(rows[-1][0], "grew")


if __name__ == "__main__":
    unittest.main()
