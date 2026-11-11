"""Space history: answers "what grew since last time?".

Three cheap records, all JSON under %LOCALAPPDATA%\\SpaceSweep\\history:
  * folder snapshots taken after every disk scan / folder analysis
    (only folders >= 50 MB down to 4 levels, so a snapshot of C: is a few hundred KB);
  * cleanup-item sizes after every Cleanup analysis (how fast caches refill);
  * free space per drive, logged at start-up and by the background check.
"""

import hashlib
import os
import shutil
import threading
import time

from . import fsutil

MIN_SIZE = 50 * 1024 * 1024
MAX_DEPTH = 4
KEEP_SNAPSHOTS = 12
KEEP_FREE_POINTS = 720
_LOCK = threading.Lock()


def _dir():
    path = os.path.join(fsutil.app_data_dir(), "history")
    os.makedirs(path, exist_ok=True)
    return path


def _rel(name):
    return os.path.join("history", name)


def root_key(root):
    norm = os.path.normcase(os.path.abspath(root)).rstrip("\\/") or root
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------- folder snapshots

def save_snapshot(kind, root, entries, total, extra=None):
    """entries: {relative_path: size}. Small folders are dropped to keep files light."""
    key = root_key(root)
    snap = {"id": int(time.time() * 1000), "time": time.time(), "total": total,
            "entries": {k: v for k, v in entries.items() if v >= MIN_SIZE or "\\" not in k}}
    if extra:
        snap.update(extra)
    with _LOCK:
        data = fsutil.load_json(_rel(f"snap-{key}.json"), None) or {"root": root, "kind": kind, "snapshots": []}
        data["root"], data["kind"] = root, kind
        data["snapshots"].append(snap)
        data["snapshots"] = data["snapshots"][-KEEP_SNAPSHOTS:]
        fsutil.save_json(_rel(f"snap-{key}.json"), data)
    return key


def snapshot_from_tree(root_node):
    """Flatten a scanner tree into {rel_path: size} for folders worth remembering."""
    out = {}
    stack = [(child, child.name, 1) for child in root_node.children]
    while stack:
        node, rel, depth = stack.pop()
        if node.size < MIN_SIZE and depth > 1:
            continue
        out[rel] = node.size
        if depth < MAX_DEPTH:
            stack.extend((c, rel + "\\" + c.name, depth + 1) for c in node.children if c.size >= MIN_SIZE)
    return out


def roots():
    result = []
    for name in sorted(os.listdir(_dir())):
        if not (name.startswith("snap-") and name.endswith(".json")):
            continue
        data = fsutil.load_json(_rel(name), None)
        if not data or not data.get("snapshots"):
            continue
        last = data["snapshots"][-1]
        result.append({"key": name[5:-5], "root": data["root"], "kind": data["kind"], "count": len(data["snapshots"]),
                       "last_time": last["time"], "last_total": last["total"], "first_time": data["snapshots"][0]["time"]})
    result.sort(key=lambda r: r["last_time"], reverse=True)
    return result


def compare(key, older_id=None, newer_id=None, limit=150):
    data = fsutil.load_json(_rel(f"snap-{os.path.basename(key)}.json"), None)
    if not data or not data.get("snapshots"):
        raise KeyError("no history")
    snaps = data["snapshots"]
    by_id = {s["id"]: s for s in snaps}
    newer = by_id.get(newer_id) or snaps[-1]
    older = by_id.get(older_id) or (snaps[-2] if len(snaps) > 1 else None)
    meta = [{"id": s["id"], "time": s["time"], "total": s["total"]} for s in snaps]
    if older is None or older["id"] == newer["id"]:
        return {"root": data["root"], "snapshots": meta, "older": None, "newer": _head(newer), "grew": [], "shrank": [], "delta": 0}

    a, b = older["entries"], newer["entries"]
    rows = []
    for path in set(a) | set(b):
        before, after = a.get(path), b.get(path)
        delta = (after or 0) - (before or 0)
        if abs(delta) >= 10 * 1024 * 1024:
            rows.append({"path": path, "before": before, "after": after, "delta": delta, "depth": path.count("\\") + 1})

    # Keep the most specific folder: drop a parent when one child explains >= 80% of its change.
    children = {}
    for r in rows:
        parent = r["path"].rsplit("\\", 1)[0] if "\\" in r["path"] else ""
        children.setdefault(parent, []).append(r)

    def explained(r):
        kids = [k for k in children.get(r["path"], []) if (k["delta"] > 0) == (r["delta"] > 0)]
        return any(abs(k["delta"]) >= 0.8 * abs(r["delta"]) for k in kids)

    keep = [r for r in rows if not explained(r)]
    for r in keep:
        r["full"] = os.path.join(data["root"], r["path"])
    grew = sorted((r for r in keep if r["delta"] > 0), key=lambda r: -r["delta"])[:limit]
    shrank = sorted((r for r in keep if r["delta"] < 0), key=lambda r: r["delta"])[:limit]
    return {"root": data["root"], "snapshots": meta, "older": _head(older), "newer": _head(newer),
            "delta": newer["total"] - older["total"], "grew": grew, "shrank": shrank}


def _head(s):
    return {"id": s["id"], "time": s["time"], "total": s["total"], "used": s.get("used"), "free": s.get("free")}


# ---------------------------------------------------------------- cleanup item sizes

def save_rule_sizes(drive, items):
    sizes = {i["id"]: i["size"] for i in items if i.get("measured") and i.get("size") is not None}
    with _LOCK:
        data = fsutil.load_json(_rel("rules.json"), {})
        series = data.setdefault(drive.upper(), [])
        series.append({"time": time.time(), "sizes": sizes})
        data[drive.upper()] = series[-KEEP_SNAPSHOTS * 2:]
        fsutil.save_json(_rel("rules.json"), data)


def rule_growth(drive):
    """Growth of each cleanup item between the oldest and newest cleanup analysis."""
    series = fsutil.load_json(_rel("rules.json"), {}).get(drive.upper(), [])
    if len(series) < 2:
        return {"since": None, "items": []}
    old, new = series[0], series[-1]
    # Measure from the snapshot right after the most recent clean-up dip, if the cache was emptied meanwhile.
    for s in series[:-1]:
        if sum(s["sizes"].values()) < sum(old["sizes"].values()):
            old = s
    items = [{"id": k, "before": old["sizes"].get(k, 0), "after": v, "delta": v - old["sizes"].get(k, 0)}
             for k, v in new["sizes"].items()]
    items = [i for i in items if i["delta"] >= 50 * 1024 * 1024]
    items.sort(key=lambda i: -i["delta"])
    return {"since": old["time"], "until": new["time"], "items": items}


# ---------------------------------------------------------------- free space

def log_free(drives=None, min_gap=3600):
    """Append (time, used, free) per fixed drive; skips if the last point is newer than min_gap seconds."""
    from .winapi import list_drives
    drives = drives if drives is not None else [d for d in list_drives() if d["type"] == "fixed"]
    now = time.time()
    with _LOCK:
        data = fsutil.load_json(_rel("free.json"), {})
        for d in drives:
            pts = data.setdefault(d["root"].upper(), [])
            point = [round(now), d["used"], d["free"]]
            if pts and now - pts[-1][0] < min_gap:
                pts[-1] = point
            else:
                pts.append(point)
            data[d["root"].upper()] = pts[-KEEP_FREE_POINTS:]
        fsutil.save_json(_rel("free.json"), data)


def free_series(drive):
    return fsutil.load_json(_rel("free.json"), {}).get(drive.upper(), [])


def used_change(drive, days=7):
    """(delta_used, since_time) vs the newest point at least `days` old (or the oldest point)."""
    pts = free_series(drive)
    if len(pts) < 2:
        return None
    try:
        now_used = shutil.disk_usage(drive).used
    except OSError:
        now_used = pts[-1][1]
    cutoff = time.time() - days * 86400
    old = next((p for p in reversed(pts) if p[0] <= cutoff), pts[0])
    return {"delta": now_used - old[1], "since": old[0]}
