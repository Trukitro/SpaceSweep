"""Exact duplicate finder.

Three stages, each one only for files that survived the previous one:
  1. same size              (free: comes from the directory listing)
  2. same first+last 64 KB   (cheap: 128 KB read per file)
  3. same full BLAKE2b hash  (reads the whole file, in parallel threads)
Only byte-for-byte identical files end up in a group. Hard links (the same
file reachable by two names) are not reported, since deleting one frees nothing.
"""

import hashlib
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from .fsutil import walk_files

EDGE = 64 * 1024
CHUNK = 1024 * 1024
SKIP_DIRS = {"$recycle.bin", "system volume information", "windows", "winsxs", "node_modules", ".git"}


def _edge_hash(path, size):
    h = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as fh:
        h.update(fh.read(EDGE))
        if size > 2 * EDGE:
            fh.seek(-EDGE, os.SEEK_END)
            h.update(fh.read(EDGE))
    return h.digest()


def _full_hash(path, job):
    h = hashlib.blake2b(digest_size=20)
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
            if job.cancelled:
                return None
    return h.hexdigest()


def _hash_groups(groups, fn, job, label, weight_start, weight_span):
    """Run fn(path) over every file in every group, regroup by result."""
    tasks = [(key, path) for key, paths in groups.items() for path in paths]
    out = defaultdict(list)
    if not tasks:
        return out
    with ThreadPoolExecutor(max_workers=4) as pool:
        def work(task):
            key, path = task
            try:
                return key, path, fn(path)
            except OSError:
                return key, path, None
        for i, (key, path, digest) in enumerate(pool.map(work, tasks), 1):
            if digest is not None:
                out[(key, digest)].append(path)
            if i % 50 == 0 or i == len(tasks):
                job.check()
                job.update(message=label, current=path, progress=weight_start + weight_span * i / len(tasks))
    return {k: v for k, v in out.items() if len(v) > 1}


def hardlink(job, pairs):
    """Replace each duplicate with a hard link to its kept twin, so both paths keep working but the
    data is stored once. pairs: [(duplicate_path, keeper_path)]. Re-verifies content before touching anything.

    A hard link is the *same* file under two names: editing one edits the other. Meant for files
    that are not edited (installers, archives, photos, videos).
    """
    results = []
    for i, (dup, keep) in enumerate(pairs, 1):
        item = {"path": dup, "keeper": keep, "ok": False, "size": 0, "error": None}
        results.append(item)
        try:
            if os.path.splitdrive(os.path.abspath(dup))[0].upper() != os.path.splitdrive(os.path.abspath(keep))[0].upper():
                raise ValueError("distinto disco: los enlaces duros solo funcionan en el mismo disco / different drive")
            a, b = os.stat(dup), os.stat(keep)
            if (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino) and a.st_ino:
                raise ValueError("ya están enlazados / already linked")
            if a.st_size != b.st_size or _full_hash(dup, job) != _full_hash(keep, job):
                raise ValueError("el contenido ya no es idéntico / content no longer identical")
            tmp = dup + ".spacesweep-link"
            os.link(keep, tmp)
            os.replace(tmp, dup)  # atomic swap: the duplicate's name now points at the kept data
            item.update(ok=True, size=a.st_size)
        except (OSError, ValueError) as exc:
            item["error"] = str(exc)
            if os.path.exists(dup + ".spacesweep-link"):
                os.remove(dup + ".spacesweep-link")
        job.check()
        job.update(progress=i / len(pairs), current=os.path.basename(dup))
    return {"results": results, "ok": sum(r["ok"] for r in results), "freed": sum(r["size"] for r in results if r["ok"])}


def find(job, folders, min_size=1024 * 1024, reference=()):
    """Exact duplicates among `folders`.

    With `reference` folders (a backup, usually on another drive) only files that
    also exist in the reference are reported, and reference files are never
    offered for deletion: "this is already backed up, you can free it here".
    """
    by_size = defaultdict(list)
    meta = {}
    is_ref = set()
    seen_roots = set()
    job.update(message="listing", progress=-1)
    count = 0

    def prune(entry):
        return entry.name.lower() in SKIP_DIRS

    # Reference folders first, so a file inside both lists counts as reference (never deletable).
    for folder, ref in [(f, True) for f in reference] + [(f, False) for f in folders]:
        root = os.path.normcase(os.path.abspath(folder))
        if root in seen_roots or not os.path.isdir(folder):
            continue
        seen_roots.add(root)
        for path, size, mtime, _ in walk_files(folder, job, prune):
            if size < min_size:
                continue
            key = os.path.normcase(path)
            if key in meta:
                continue  # overlapping folders were selected
            meta[key] = (path, size, mtime)
            by_size[size].append(key)
            if ref:
                is_ref.add(key)
            count += 1
            if count % 1000 == 0:
                job.update(count=count)
    job.update(count=count)

    if reference:
        candidates = {s: p for s, p in by_size.items()
                      if any(k in is_ref for k in p) and any(k not in is_ref for k in p)}
    else:
        candidates = {s: p for s, p in by_size.items() if len(p) > 1}
    # Drop hard links: same file id means same data on disk.
    for size, keys in list(candidates.items()):
        ids, unique = set(), []
        for k in keys:
            try:
                st = os.stat(meta[k][0])
                fid = (st.st_dev, st.st_ino)
            except OSError:
                continue
            if fid[1] and fid in ids:
                continue
            ids.add(fid)
            unique.append(k)
        if len(unique) > 1:
            candidates[size] = unique
        else:
            del candidates[size]

    stage2 = _hash_groups(candidates, lambda k: _edge_hash(meta[k][0], meta[k][1]), job, "quick-hash", 0.0, 0.3)
    stage3 = _hash_groups(stage2, lambda k: _full_hash(meta[k][0], job), job, "full-hash", 0.3, 0.7)

    groups = []
    for (_, digest), keys in stage3.items():
        refs = [k for k in keys if k in is_ref]
        if reference and (not refs or len(refs) == len(keys)):
            continue
        files = sorted(({"path": meta[k][0], "mtime": meta[k][2], "ref": k in is_ref} for k in keys),
                       key=lambda f: (not f["ref"], f["mtime"]))
        size = meta[keys[0]][1]
        freeable = len(keys) - len(refs) if reference else len(keys) - 1
        groups.append({"hash": digest, "size": size, "count": len(files), "wasted": size * freeable, "files": files})
    groups.sort(key=lambda g: g["wasted"], reverse=True)
    return {
        "reference": list(reference),
        "folders": list(folders),
        "scanned": count,
        "groups": groups[:2000],
        "total_groups": len(groups),
        "wasted": sum(g["wasted"] for g in groups),
    }
