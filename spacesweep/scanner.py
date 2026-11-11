"""Disk explorer: one pass over a drive or folder, then instant drill-down.

Only directories are kept in memory (files are aggregated into their folder
and re-listed on demand), so even a 2-million-file system drive stays at a
few dozen MB. Top-level folders are scanned in parallel threads: scandir
releases the GIL while it waits on the disk, so SSDs get noticeably faster.
"""

import heapq
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from .fsutil import is_link_entry
from .winapi import disk_free

TOP_FILES = 200
TOP_EXTS = 25


class Node:
    __slots__ = ("name", "size", "files", "children", "parent", "denied")

    def __init__(self, name, parent=None):
        self.name = name
        self.size = 0
        self.files = 0
        self.children = []
        self.parent = parent
        self.denied = False


class ScanResult:
    def __init__(self, root):
        self.id = uuid.uuid4().hex[:10]
        self.root_path = root
        self.root = Node(root)
        self.largest = []  # min-heap of (size, path)
        self.exts = {}
        self.denied_dirs = 0
        self.seconds = 0.0


_SCANS = {}
_SCANS_LOCK = threading.Lock()


def ext_of(name):
    """Lower-case extension without the dot; '' for none or for absurdly long 'extensions'."""
    dot = name.rfind(".")
    if dot <= 0 or len(name) - dot > 11:
        return ""
    return name[dot + 1:].lower()


def get_scan(scan_id):
    return _SCANS.get(scan_id)


def _scan_subtree(path, node, job, counter, lock):
    """Walk one top-level folder. Returns (largest_heap, ext_totals, denied, created_nodes)."""
    largest, exts, denied = [], {}, 0
    order = [node]
    stack = [(path, node)]
    local = 0
    while stack:
        current, cur_node = stack.pop()
        try:
            it = os.scandir(current)
        except OSError:
            cur_node.denied = True
            denied += 1
            continue
        with it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if is_link_entry(entry):
                            continue
                        child = Node(entry.name, cur_node)
                        cur_node.children.append(child)
                        order.append(child)
                        stack.append((entry.path, child))
                        continue
                    size = entry.stat(follow_symlinks=False).st_size
                except OSError:
                    continue
                cur_node.size += size
                cur_node.files += 1
                if len(largest) < TOP_FILES:
                    heapq.heappush(largest, (size, entry.path))
                elif size > largest[0][0]:
                    heapq.heapreplace(largest, (size, entry.path))
                ext = ext_of(entry.name)
                tot = exts.get(ext)
                if tot is None:
                    exts[ext] = [size, 1]
                else:
                    tot[0] += size
                    tot[1] += 1
                local += 1
                if local >= 1000:
                    with lock:
                        counter[0] += local
                    local = 0
                    job.check()
                    job.update(current=current, count=counter[0])
    with lock:
        counter[0] += local
    return largest, exts, denied, order


def scan(job, root):
    started = time.time()
    root = os.path.abspath(root)
    result = ScanResult(root)
    counter, lock = [0], threading.Lock()
    job.update(message="scanning", current=root)

    top_dirs = []
    try:
        with os.scandir(root) as it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if not is_link_entry(entry):
                            child = Node(entry.name, result.root)
                            result.root.children.append(child)
                            top_dirs.append((entry.path, child))
                    else:
                        size = entry.stat(follow_symlinks=False).st_size
                        result.root.size += size
                        result.root.files += 1
                        heapq.heappush(result.largest, (size, entry.path))
                except OSError:
                    continue
    except OSError as exc:
        raise RuntimeError(f"No se puede leer / cannot read {root}: {exc}") from exc

    all_nodes = []
    workers = min(8, (os.cpu_count() or 4) + 2)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_scan_subtree, p, n, job, counter, lock) for p, n in top_dirs]
        for done_i, fut in enumerate(futures, 1):
            largest, exts, denied, order = fut.result()
            all_nodes.extend(order)
            result.denied_dirs += denied
            for item in largest:
                if len(result.largest) < TOP_FILES:
                    heapq.heappush(result.largest, item)
                elif item[0] > result.largest[0][0]:
                    heapq.heapreplace(result.largest, item)
            for ext, (size, count) in exts.items():
                tot = result.exts.setdefault(ext, [0, 0])
                tot[0] += size
                tot[1] += count
            job.update(progress=done_i / max(1, len(futures)))

    # Children were created after their parents, so a reverse pass sums bottom-up.
    for node in reversed(all_nodes):
        if node.parent is not None:
            node.parent.size += node.size
            node.parent.files += node.files

    result.seconds = round(time.time() - started, 1)
    try:
        import shutil
        from . import history
        extra = {}
        if os.path.splitdrive(root)[1] in ("\\", ""):
            usage = shutil.disk_usage(root)
            extra = {"used": usage.used, "free": usage.free}
        history.save_snapshot("scan", root, history.snapshot_from_tree(result.root), result.root.size, extra)
    except OSError:
        pass  # history is a bonus; never fail a scan because of it
    with _SCANS_LOCK:
        _SCANS[result.id] = result
        for old in list(_SCANS)[:-3]:  # keep memory bounded: last 3 scans
            del _SCANS[old]
    return summary(result)


def _find(result, rel):
    node = result.root
    for part in [p for p in rel.replace("/", "\\").split("\\") if p]:
        node = next((c for c in node.children if c.name == part), None)
        if node is None:
            raise KeyError(rel)
    return node


def summary(result):
    root = result.root_path
    drive_root = os.path.splitdrive(root)[0] + "\\"
    is_drive = os.path.normcase(root.rstrip("\\") + "\\") == os.path.normcase(drive_root)
    unaccounted = None
    if is_drive:
        import shutil
        try:
            usage = shutil.disk_usage(drive_root)
            unaccounted = max(0, usage.used - result.root.size)
        except OSError:
            pass
    exts = sorted(result.exts.items(), key=lambda kv: kv[1][0], reverse=True)[:TOP_EXTS]
    return {
        "scan_id": result.id,
        "root": root,
        "is_drive": is_drive,
        "total": result.root.size,
        "files": result.root.files,
        "denied_dirs": result.denied_dirs,
        "unaccounted": unaccounted,
        "free": disk_free(drive_root),
        "seconds": result.seconds,
        "largest": [{"path": p, "size": s} for s, p in sorted(result.largest, reverse=True)],
        "exts": [{"ext": e or "", "size": s, "files": c} for e, (s, c) in exts],
    }


def children(scan_id, rel=""):
    result = get_scan(scan_id)
    if result is None:
        raise KeyError("scan expired")
    node = _find(result, rel)
    abs_path = os.path.join(result.root_path, rel) if rel else result.root_path
    dirs = sorted(node.children, key=lambda n: n.size, reverse=True)
    files = []
    try:
        with os.scandir(abs_path) as it:
            for e in it:
                try:
                    if e.is_file(follow_symlinks=False):
                        st = e.stat(follow_symlinks=False)
                        files.append({"name": e.name, "path": e.path, "size": st.st_size, "mtime": st.st_mtime})
                except OSError:
                    continue
    except OSError:
        pass
    files.sort(key=lambda f: f["size"], reverse=True)
    return {
        "rel": rel,
        "path": abs_path,
        "size": node.size,
        "files_total": node.files,
        "denied": node.denied,
        "dirs": [{"name": c.name, "size": c.size, "files": c.files, "denied": c.denied,
                  "path": os.path.join(abs_path, c.name)} for c in dirs[:400]],
        "files": files[:150],
        "more_files": max(0, len(files) - 150),
    }
