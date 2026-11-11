"""Fast filesystem helpers shared by every module.

`os.scandir` on Windows returns size, timestamps and attributes straight
from the directory listing, so walking with it needs no extra stat() calls
per file. That is what makes a pure-Python scan of a whole drive feasible.
"""

import json
import os
import stat
import time

from . import APP_NAME, winapi

FILE_ATTRIBUTE_REPARSE_POINT = 0x400
DAY = 86400


def app_data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def load_json(name, default):
    try:
        with open(os.path.join(app_data_dir(), name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def save_json(name, data):
    path = os.path.join(app_data_dir(), name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def is_link_entry(entry):
    """Symlinks and junctions: never follow them (loops, double counting, deleting outside the target)."""
    try:
        if entry.is_symlink():
            return True
        attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
        return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return True


def is_link_path(path):
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)


def walk_files(root, job=None, prune=None):
    """Yield (path, size, mtime, name) for every regular file under root.

    `prune(dir_entry)` may return True to skip a directory entirely.
    """
    stack = [root]
    n = 0
    while stack:
        current = stack.pop()
        try:
            it = os.scandir(current)
        except OSError:
            continue
        with it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if is_link_entry(entry) or (prune and prune(entry)):
                            continue
                        stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        st = entry.stat(follow_symlinks=False)
                        yield entry.path, st.st_size, st.st_mtime, entry.name
                except OSError:
                    continue
                n += 1
                if job and n % 2000 == 0:
                    job.check()
                    job.update(current=current)


def dir_size(path, older_than_days=0, job=None):
    """(bytes, files) under path; with older_than_days only files not modified since then count."""
    cutoff = time.time() - older_than_days * DAY if older_than_days else None
    total = count = 0
    if os.path.isfile(path):
        try:
            st = os.stat(path)
        except OSError:
            return 0, 0
        if cutoff is None or st.st_mtime < cutoff:
            return st.st_size, 1
        return 0, 0
    for _, size, mtime, _ in walk_files(path, job):
        if cutoff is None or mtime < cutoff:
            total += size
            count += 1
    return total, count


# ---------------------------------------------------------------- safety

def _norm(path):
    return os.path.normcase(os.path.abspath(path)).rstrip("\\/")


def protected_paths():
    """Folders that must never be deleted themselves (their contents may be, if a rule says so)."""
    env = os.environ
    candidates = [
        env.get("SystemRoot", r"C:\Windows"),
        os.path.join(env.get("SystemRoot", r"C:\Windows"), "System32"),
        env.get("ProgramFiles", r"C:\Program Files"),
        env.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        env.get("ProgramData", r"C:\ProgramData"),
        os.path.dirname(os.path.expanduser("~")),  # C:\Users
        os.path.expanduser("~"),
        env.get("APPDATA", ""),
        env.get("LOCALAPPDATA", ""),
    ]
    candidates += list(winapi.user_folders().values())
    return {_norm(p) for p in candidates if p}


def check_deletable(path):
    """Raise ValueError if deleting `path` itself could damage Windows or a user profile."""
    norm = _norm(path)
    if len(norm) <= 3 or os.path.splitdrive(norm)[1] in ("", "\\", "/"):
        raise ValueError(f"Refusing to delete a drive root: {path}")
    if norm in protected_paths():
        raise ValueError(f"Refusing to delete a protected folder: {path}")
    win = _norm(os.environ.get("SystemRoot", r"C:\Windows"))
    if norm.startswith(win + os.sep) and "\\temp" not in norm and "softwaredistribution" not in norm:
        raise ValueError(f"Refusing to delete inside Windows: {path}")


def _remove_file(path):
    try:
        os.remove(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)  # clear read-only and retry once
        os.remove(path)


def delete_contents(root, older_than_days=0, job=None, on_progress=None):
    """Delete everything inside root (root itself stays). Files in use are skipped, not forced.

    Returns (freed_bytes, deleted_files, skipped_files).
    """
    cutoff = time.time() - older_than_days * DAY if older_than_days else None
    freed = deleted = skipped = 0
    if not os.path.isdir(root) or is_link_path(root):
        return 0, 0, 0
    dirs = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            it = os.scandir(current)
        except OSError:
            skipped += 1
            continue
        with it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False) and not is_link_entry(entry):
                        stack.append(entry.path)
                        dirs.append(entry.path)
                        continue
                    st = entry.stat(follow_symlinks=False)
                    if cutoff is not None and st.st_mtime >= cutoff:
                        continue
                    if is_link_entry(entry):
                        try:
                            os.rmdir(entry.path)  # junction / dir symlink: removes the link only
                        except OSError:
                            os.unlink(entry.path)  # file symlink
                    else:
                        _remove_file(entry.path)
                    freed += st.st_size
                    deleted += 1
                except OSError:
                    skipped += 1
                if job and (deleted + skipped) % 500 == 0:
                    job.check()
                    if on_progress:
                        on_progress(freed, deleted)
    for d in sorted(dirs, key=len, reverse=True):  # deepest first; only empty ones go
        try:
            os.rmdir(d)
        except OSError:
            pass
    return freed, deleted, skipped


def delete_paths(paths, permanent=False):
    """Delete user-chosen files/folders. Default goes to the Recycle Bin.

    Returns a list of {path, ok, size, error}.
    """
    results = []
    to_recycle = []
    for p in paths:
        item = {"path": p, "ok": False, "size": 0, "error": None}
        results.append(item)
        try:
            check_deletable(p)
            if not os.path.exists(p):
                raise FileNotFoundError("ya no existe / no longer exists")
            item["size"] = dir_size(p)[0]
        except (ValueError, OSError) as exc:
            item["error"] = str(exc)
            continue
        if permanent:
            try:
                if os.path.isdir(p) and not is_link_path(p):
                    delete_contents(p)
                    os.rmdir(p)
                else:
                    _remove_file(p)
                item["ok"] = True
            except OSError as exc:
                item["error"] = str(exc)
        else:
            to_recycle.append(item)
    # One shell call per batch is much faster than one per file.
    for i in range(0, len(to_recycle), 200):
        batch = to_recycle[i:i + 200]
        try:
            winapi.send_to_recycle_bin([b["path"] for b in batch])
        except OSError as exc:
            for b in batch:
                b["error"] = str(exc)
            continue
        for b in batch:
            b["ok"] = not os.path.exists(b["path"])
            if not b["ok"]:
                b["error"] = "en uso o sin permiso / in use or access denied"
    return results


def unique_target(path):
    """'file.txt' -> 'file (2).txt' if taken."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"
