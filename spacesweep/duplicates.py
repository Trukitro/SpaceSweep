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


def find(job, folders, min_size=1024 * 1024):
    by_size = defaultdict(list)
    meta = {}
    seen_roots = set()
    job.update(message="listing", progress=-1)
    count = 0

    def prune(entry):
        return entry.name.lower() in SKIP_DIRS

    for folder in folders:
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
            count += 1
            if count % 1000 == 0:
                job.update(count=count)
    job.update(count=count)

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
        files = sorted(({"path": meta[k][0], "mtime": meta[k][2]} for k in keys), key=lambda f: f["mtime"])
        size = meta[keys[0]][1]
        groups.append({"hash": digest, "size": size, "count": len(files), "wasted": size * (len(files) - 1), "files": files})
    groups.sort(key=lambda g: g["wasted"], reverse=True)
    return {
        "folders": list(folders),
        "scanned": count,
        "groups": groups[:2000],
        "total_groups": len(groups),
        "wasted": sum(g["wasted"] for g in groups),
    }
