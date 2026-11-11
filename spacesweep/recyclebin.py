"""Smart Recycle Bin: empty only what has been there longer than N days.

Each deleted item is a pair in $Recycle.Bin\\<your SID>: $Ixxxx (metadata: original
path, size, deletion time) and $Rxxxx (the content, file or folder). Windows'
own 'Empty Recycle Bin' is all-or-nothing; reading the $I files lets us keep
recent deletions (the ones you may still want back).
"""

import os
import struct
import time

from . import fsutil, winapi

FILETIME_EPOCH = 11644473600  # seconds between 1601-01-01 and 1970-01-01


def parse_info(data):
    """$I file -> (original_path, size, deleted_unix_time) or None. Supports format v1 (Vista-8) and v2 (10+)."""
    if len(data) < 24:
        return None
    version, size, ft = struct.unpack_from("<qqq", data, 0)
    deleted = ft / 10_000_000 - FILETIME_EPOCH
    if version == 2 and len(data) >= 28:
        (n,) = struct.unpack_from("<i", data, 24)
        path = data[28:28 + n * 2].decode("utf-16-le", "replace").rstrip("\0")
    elif version == 1:
        path = data[24:24 + 520].decode("utf-16-le", "replace").split("\0", 1)[0]
    else:
        return None
    return path, size, deleted


def _bins():
    """$Recycle.Bin folders we can read (our own SID folder on every fixed drive)."""
    out = []
    for d in winapi.list_drives():
        if d["type"] not in ("fixed", "removable"):
            continue
        root = os.path.join(d["root"], "$Recycle.Bin")
        try:
            subs = [e.path for e in os.scandir(root) if e.is_dir(follow_symlinks=False)]
        except OSError:
            continue
        for s in subs:
            try:
                os.listdir(s)
                out.append(s)
            except OSError:
                continue  # other users' bins are not readable, as intended
    return out


def items(bins=None):
    now = time.time()
    out = []
    for b in bins if bins is not None else _bins():
        try:
            entries = os.listdir(b)
        except OSError:
            continue
        for name in entries:
            if not name.startswith("$I"):
                continue
            ipath = os.path.join(b, name)
            rpath = os.path.join(b, "$R" + name[2:])
            try:
                with open(ipath, "rb") as fh:
                    meta = parse_info(fh.read())
            except OSError:
                continue
            if not meta or not os.path.lexists(rpath):
                continue
            original, size, deleted = meta
            if os.path.isdir(rpath):
                size = fsutil.dir_size(rpath)[0]
            out.append({"name": os.path.basename(original) or original, "original": original, "size": size,
                        "deleted": deleted, "age_days": int((now - deleted) // 86400), "drive": original[:2].upper(),
                        "info": ipath, "data": rpath})
    out.sort(key=lambda i: i["deleted"])
    return out


def summary(bins=None):
    its = items(bins)
    buckets = {}
    for limit in (7, 30, 90, 365):
        old = [i for i in its if i["age_days"] >= limit]
        buckets[str(limit)] = {"count": len(old), "size": sum(i["size"] for i in old)}
    return {"count": len(its), "size": sum(i["size"] for i in its), "older_than": buckets, "items": its[-300:][::-1]}


def empty_older_than(days, bins=None, job=None):
    """Permanently delete Recycle Bin items deleted more than `days` days ago."""
    freed = removed = failed = 0
    for i in items(bins):
        if i["age_days"] < days:
            continue
        try:
            if os.path.isdir(i["data"]) and not fsutil.is_link_path(i["data"]):
                fsutil.delete_contents(fsutil.long_path(i["data"]))
                os.rmdir(fsutil.long_path(i["data"]))
            else:
                os.remove(fsutil.long_path(i["data"]))
            os.remove(i["info"])
            freed += i["size"]
            removed += 1
        except OSError:
            failed += 1
        if job and (removed + failed) % 50 == 0:
            job.check()
    return {"freed": freed, "removed": removed, "failed": failed, "days": days}
