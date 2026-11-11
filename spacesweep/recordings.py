"""Game recordings and screen captures: the gigabytes people forget about.

Looks where capture tools save by default (and where their settings say):
Xbox Game Bar (Videos\\Captures), NVIDIA ShadowPlay / Instant Replay, OBS
Studio (every profile's recording path), Steam game recordings and screenshots.
"""

import configparser
import glob
import os
import time

from . import winapi
from .fsutil import walk_files
from .scanner import ext_of

VIDEO = {"mp4", "mkv", "mov", "flv", "webm", "avi", "ts", "m4v"}
IMAGE = {"png", "jpg", "jpeg", "jxr", "bmp"}
DAY = 86400


def _nvidia_paths():
    paths = []
    if winapi.IS_WINDOWS:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\NVIDIA Corporation\Global\ShadowPlay\NVSPCAPS") as key:
                for value in ("DefaultPathW", "TempFilePath"):
                    try:
                        raw = winreg.QueryValueEx(key, value)[0]
                        text = raw.decode("utf-16-le", "ignore") if isinstance(raw, bytes) else str(raw)
                        text = text.split("\0", 1)[0].strip()
                        if text:
                            paths.append(text)
                    except OSError:
                        pass
        except OSError:
            pass
    paths.append(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp", "Highlights"))
    return paths


def _obs_paths():
    out = []
    for ini in glob.glob(os.path.join(os.environ.get("APPDATA", ""), "obs-studio", "basic", "profiles", "*", "basic.ini")):
        cp = configparser.ConfigParser(strict=False, interpolation=None)
        try:
            cp.read(ini, encoding="utf-8-sig")
        except (configparser.Error, OSError):
            continue
        for section, key in (("SimpleOutput", "FilePath"), ("AdvOut", "RecFilePath"), ("AdvOut", "FFFilePath")):
            if cp.has_option(section, key):
                out.append(cp.get(section, key).replace("/", "\\"))
    return out


def sources():
    videos = winapi.known_folder("videos")
    srcs = [("Xbox Game Bar", os.path.join(videos, "Captures"), VIDEO | IMAGE)]
    srcs += [("NVIDIA", p, VIDEO) for p in _nvidia_paths()]
    srcs += [("OBS Studio", p, VIDEO) for p in _obs_paths()]
    steam = None
    if winapi.IS_WINDOWS:
        from .inventory import _steam_root
        steam = _steam_root()
    if steam:
        srcs += [("Steam", p, VIDEO) for p in glob.glob(os.path.join(steam, "userdata", "*", "gamerecordings"))]
        srcs += [("Steam", p, IMAGE) for p in glob.glob(os.path.join(steam, "userdata", "*", "760", "remote"))]
    # Never treat a whole temp folder as a capture folder (NVIDIA's TempFilePath often points at %TEMP%).
    temp_roots = {os.path.normcase(os.path.abspath(p)) for p in (os.environ.get("TEMP", ""), os.environ.get("TMP", ""),
                  os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp")) if p}
    seen, out = set(), []
    for app, path, exts in srcs:
        path = os.path.normpath(path) if path else path  # OBS stores C:\\Users\\... with doubled separators
        key = os.path.normcase(os.path.abspath(path)) if path else ""
        if path and os.path.isdir(path) and key not in seen and key not in temp_roots:
            seen.add(key)
            out.append((app, path, exts))
    return out


def scan(job, min_size=5 * 1024 * 1024):
    now = time.time()
    result = []
    for app, path, exts in sources():
        job.check()
        job.update(current=path)
        files = [{"path": p, "size": s, "mtime": m, "age_days": int((now - m) // DAY)}
                 for p, s, m, n in walk_files(path, job) if ext_of(n) in exts and s >= (min_size if ext_of(n) in VIDEO else 0)]
        if not files:
            continue
        files.sort(key=lambda f: -f["size"])
        result.append({"app": app, "path": path, "count": len(files), "size": sum(f["size"] for f in files),
                       "older_90": sum(f["size"] for f in files if f["age_days"] >= 90), "files": files[:500]})
    result.sort(key=lambda r: -r["size"])
    return {"sources": result, "total": sum(r["size"] for r in result)}
