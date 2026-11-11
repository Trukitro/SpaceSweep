"""Move a heavy folder to another drive and leave a directory junction behind.

Programs keep using the old path (C:\\Users\\me\\.lmstudio\\models) while the bytes
live on another drive (J:\\SpaceSweep\\...). Junctions need no administrator rights.

Order of operations, so a failure at any step leaves the original untouched:
  1. checks: not protected, not a link, target drive is NTFS and has room
  2. lock test: rename the folder and back (fails if a program has files open)
  3. copy everything to the target, then verify file count and total bytes
  4. rename the original to "<name>.spacesweep-old" (instant, same drive)
  5. create the junction; if that fails, rename the original back
  6. only now delete the old copy
"""

import ctypes
import os
import shutil
import time

from . import fsutil, winapi
from .fsutil import is_link_path, long_path

RECORDS = "moves.json"
OLD_SUFFIX = ".spacesweep-old"
MARGIN = 512 * 1024 * 1024


def _fs_type(root):
    if not winapi.IS_WINDOWS:
        return "unknown"
    buf = ctypes.create_unicode_buffer(64)
    ok = winapi._kernel32.GetVolumeInformationW(root, None, 0, None, None, None, buf, 64)
    return buf.value if ok else ""


def _drive(path):
    return os.path.splitdrive(os.path.abspath(path))[0].upper()


def check(src, dest_root):
    """Return (size, files, target) or raise ValueError with a user-facing reason."""
    src = os.path.abspath(src)
    if not os.path.isdir(src):
        raise ValueError("La carpeta no existe / folder not found")
    if is_link_path(src):
        raise ValueError("Ya es un enlace (¿ya se movió?) / already a link")
    fsutil.check_deletable(src)
    for p in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", ""), os.environ.get("SystemRoot", "")):
        if p and os.path.normcase(src).startswith(os.path.normcase(p) + os.sep):
            raise ValueError("No se mueven carpetas de Program Files ni de Windows / Program Files and Windows are not moved")
    dest_root = os.path.abspath(dest_root)
    if _drive(dest_root) == _drive(src):
        raise ValueError("Elige otro disco / pick a different drive")
    fs = _fs_type(_drive(dest_root) + "\\")
    if winapi.IS_WINDOWS and fs.upper() != "NTFS":
        raise ValueError(f"El disco destino es {fs or '?'}; los enlaces necesitan NTFS / target must be NTFS")
    size, files = fsutil.dir_size(long_path(src))
    if shutil.disk_usage(_drive(dest_root) + "\\").free < size + MARGIN:
        raise ValueError("No hay espacio suficiente en el disco destino / not enough space on the target drive")
    target = fsutil.unique_target(os.path.join(dest_root, os.path.basename(src.rstrip("\\/")) or "folder"))
    return size, files, target


def _has_links(root):
    stack = [root]
    while stack:
        cur = stack.pop()
        with os.scandir(cur) as it:
            for e in it:
                if fsutil.is_link_entry(e):
                    return True
                if e.is_dir(follow_symlinks=False):
                    stack.append(e.path)
    return False


def _copy_tree(src, dst, job, total):
    done = 0
    for cur, dirs, files in os.walk(long_path(src)):
        rel = os.path.relpath(cur, long_path(src))
        out = os.path.join(long_path(dst), rel) if rel != "." else long_path(dst)
        os.makedirs(out, exist_ok=True)
        for name in files:
            shutil.copy2(os.path.join(cur, name), os.path.join(out, name))
            done += os.path.getsize(os.path.join(out, name))
            if job:
                job.check()
                job.update(progress=done / max(1, total), current=name)
        shutil.copystat(cur, out)


def _make_junction(link, target):
    rc, out = winapi.run_hidden(["cmd", "/c", "mklink", "/J", link, target], timeout=60)
    if rc != 0 or not os.path.isdir(link):
        raise OSError(f"mklink failed: {out.strip()}")


def move(job, src, dest_root):
    src = os.path.abspath(src)
    size, files, target = check(src, dest_root)
    if _has_links(src):
        raise ValueError("La carpeta contiene enlaces; no se mueve por seguridad / folder contains links")
    probe = src + ".spacesweep-locktest"
    try:
        os.rename(src, probe)
        os.rename(probe, src)
    except OSError as exc:
        raise ValueError(f"Hay archivos en uso: cierra el programa que usa esta carpeta / files in use ({exc})") from exc
    if job:
        job.update(message="copying", progress=0)
    try:
        _copy_tree(src, target, job, size)
        if fsutil.dir_size(long_path(target))[:2] != (size, files):
            raise OSError("La copia no coincide / copy verification failed")
    except BaseException:
        shutil.rmtree(long_path(target), ignore_errors=True)
        raise
    old = src + OLD_SUFFIX
    os.rename(src, old)
    try:
        _make_junction(src, target)
    except OSError:
        os.rename(old, src)
        shutil.rmtree(long_path(target), ignore_errors=True)
        raise
    if job:
        job.update(message="cleaning", progress=-1)
    fsutil.delete_contents(long_path(old))
    try:
        os.rmdir(long_path(old))
    except OSError:
        pass
    _record({"src": src, "target": target, "size": size, "files": files, "time": time.time()})
    return {"src": src, "target": target, "size": size, "files": files,
            "leftover": os.path.exists(old)}


def restore(job, src):
    """Bring a moved folder back: remove the junction, copy the data home, delete the target copy."""
    src = os.path.abspath(src)
    rec = next((r for r in list_moves() if os.path.normcase(r["src"]) == os.path.normcase(src)), None)
    if not rec:
        raise ValueError("No hay registro de ese movimiento / no record of that move")
    target = rec["target"]
    if not os.path.isdir(target):
        raise ValueError("La copia en el otro disco ya no existe / target copy is missing")
    if os.path.lexists(src) and not is_link_path(src):
        raise ValueError("Ya hay una carpeta normal en la ruta original / a real folder exists at the original path")
    size, files = fsutil.dir_size(long_path(target))
    if shutil.disk_usage(_drive(src) + "\\").free < size + MARGIN:
        raise ValueError("No hay espacio suficiente para traerla de vuelta / not enough space to bring it back")
    if os.path.lexists(src):
        os.rmdir(src)  # removes only the junction
    staging = src + ".spacesweep-restoring"
    try:
        _copy_tree(target, staging, job, size)
        if fsutil.dir_size(long_path(staging))[:2] != (size, files):
            raise OSError("La copia no coincide / copy verification failed")
        os.rename(staging, src)
    except BaseException:
        shutil.rmtree(long_path(staging), ignore_errors=True)
        if not os.path.lexists(src):
            _make_junction(src, target)  # put things back as they were
        raise
    fsutil.delete_contents(long_path(target))
    try:
        os.rmdir(long_path(target))
    except OSError:
        pass
    data = [r for r in fsutil.load_json(RECORDS, []) if os.path.normcase(r["src"]) != os.path.normcase(src)]
    fsutil.save_json(RECORDS, data)
    return {"src": src, "size": size}


def _record(rec):
    data = [r for r in fsutil.load_json(RECORDS, []) if os.path.normcase(r["src"]) != os.path.normcase(rec["src"])]
    data.append(rec)
    fsutil.save_json(RECORDS, data)


def list_moves():
    out = []
    for r in fsutil.load_json(RECORDS, []):
        r = dict(r)
        r["linked"] = is_link_path(r["src"]) and os.path.isdir(r["src"])
        r["target_ok"] = os.path.isdir(r["target"])
        out.append(r)
    return out


def suggestions():
    """Big folders that are classic candidates for living on another drive."""
    home = os.path.expanduser("~")
    cands = [
        (os.path.join(home, ".lmstudio", "models"), "ai"), (os.path.join(home, ".ollama", "models"), "ai"),
        (os.path.join(home, ".cache", "huggingface"), "ai"), (os.path.join(home, ".lmstudio", "extensions"), "ai"),
        (os.path.join(home, ".gradle"), "dev"), (os.path.join(home, ".m2"), "dev"), (os.path.join(home, ".cargo"), "dev"),
        (os.path.join(home, ".rustup"), "dev"), (os.path.join(home, ".nuget", "packages"), "dev"),
        (os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk"), "dev"),
    ]
    moved = {os.path.normcase(r["src"]) for r in fsutil.load_json(RECORDS, [])}
    out = []
    for path, kind in cands:
        if os.path.isdir(path) and not is_link_path(path) and os.path.normcase(path) not in moved:
            size = fsutil.dir_size(path)[0]
            if size >= 500 * 1024 * 1024:
                out.append({"path": path, "kind": kind, "size": size})
    out.sort(key=lambda x: -x["size"])
    return out
