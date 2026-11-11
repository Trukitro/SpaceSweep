"""Windows component store (WinSxS) through DISM, the only safe way to shrink it.

  analyze -> Dism /Online /Cleanup-Image /AnalyzeComponentStore
  clean   -> Dism /Online /Cleanup-Image /StartComponentCleanup
No /ResetBase: installed updates stay uninstallable. Both need administrator rights.
"""

import os
import re

from . import winapi

DISM = ["Dism.exe", "/Online", "/Cleanup-Image", "/English"]


def parse_analysis(text):
    """'Key : Value' lines of AnalyzeComponentStore output -> dict, plus a 'recommended' flag."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\s*([A-Za-z][\w ()/-]+?)\s*:\s*(.+?)\s*$", line)
        if m and not m.group(1).lower().startswith(("deployment image", "version", "image version")):
            out[m.group(1).strip()] = m.group(2).strip()
    rec = next((v for k, v in out.items() if "cleanup recommended" in k.lower()), "")
    out["recommended"] = rec.lower().startswith(("yes", "sí", "si"))
    return out


def analyze(job=None):
    if not winapi.is_admin():
        raise PermissionError("Requiere administrador / needs administrator")
    if job:
        job.update(message="dism-analyze", progress=-1)
    rc, out = winapi.run_hidden(DISM + ["/AnalyzeComponentStore"], timeout=900)
    if rc != 0:
        raise RuntimeError(out.strip()[-500:])
    return parse_analysis(out)


def cleanup(job=None):
    if not winapi.is_admin():
        raise PermissionError("Requiere administrador / needs administrator")
    if job:
        job.update(message="dism-clean", progress=-1)
    before = winapi.disk_free(os.environ.get("SystemDrive", "C:") + "\\")
    rc, out = winapi.run_hidden(DISM + ["/StartComponentCleanup"], timeout=3600)
    after = winapi.disk_free(os.environ.get("SystemDrive", "C:") + "\\")
    if rc != 0:
        raise RuntimeError(out.strip()[-500:])
    return {"freed": max(0, after - before), "output": out.strip()[-300:]}
