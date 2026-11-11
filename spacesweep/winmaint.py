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


def restore_points():
    """System restore points (volume shadow copies) with dates, plus the space they use. Needs admin."""
    if not winapi.is_admin():
        raise PermissionError("Requiere administrador / needs administrator")
    script = ("$s = Get-CimInstance Win32_ShadowCopy | Sort-Object InstallDate | "
              "Select-Object ID, VolumeName, @{n='Date';e={$_.InstallDate.ToString('s')}}; "
              "$st = Get-CimInstance Win32_ShadowStorage | Select-Object UsedSpace, MaxSpace, AllocatedSpace; "
              "[pscustomobject]@{points=@($s); storage=@($st)} | ConvertTo-Json -Depth 4 -Compress")
    rc, out = winapi.run_hidden(["powershell", "-NoProfile", "-Command", script], timeout=60)
    if rc != 0:
        raise RuntimeError(out.strip()[-300:])
    import json
    data = json.loads(out.strip() or "{}")
    storage = data.get("storage") or []
    return {"points": data.get("points") or [], "used": sum(int(s.get("UsedSpace") or 0) for s in storage),
            "max": sum(int(s.get("MaxSpace") or 0) for s in storage)}


def delete_oldest_restore_point(drive="C:"):
    if not winapi.is_admin():
        raise PermissionError("Requiere administrador / needs administrator")
    if not re.fullmatch(r"[A-Za-z]:", drive):
        raise ValueError(drive)
    before = restore_points()
    rc, out = winapi.run_hidden(["vssadmin", "delete", "shadows", f"/for={drive}", "/oldest", "/quiet"], timeout=300)
    if rc != 0:
        raise RuntimeError(out.strip()[-300:])
    after = restore_points()
    return {"freed": max(0, before["used"] - after["used"]), "left": len(after["points"])}


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
