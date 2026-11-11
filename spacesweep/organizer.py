"""Folder organizer: Downloads by file type, Photos/Videos by date.

Nothing moves until the user reviews the plan. Every applied plan is written
to an undo log first, so "Undo" puts each file back where it was.
"""

import os
import re
import struct
import time
import uuid
from collections import defaultdict
from datetime import datetime

from . import fsutil
from .duplicates import _full_hash
from .scanner import ext_of

DAY = 86400

CATEGORIES = {
    "installers": (("exe", "msi", "msix", "msixbundle", "appx", "appxbundle"), "Instaladores", "Installers"),
    "archives": (("zip", "rar", "7z", "tar", "gz", "tgz", "bz2", "xz", "zst"), "Comprimidos", "Archives"),
    "diskimages": (("iso", "img", "vhd", "vhdx", "dmg"), "Imágenes de disco", "Disk images"),
    "documents": (("pdf", "doc", "docx", "odt", "rtf", "txt", "md", "xls", "xlsx", "xlsm", "csv", "ods",
                   "ppt", "pptx", "odp", "epub", "pages", "numbers", "key"), "Documentos", "Documents"),
    "images": (("jpg", "jpeg", "png", "gif", "webp", "bmp", "tif", "tiff", "heic", "heif", "svg", "ico",
                "raw", "cr2", "cr3", "nef", "arw", "dng", "psd", "avif"), "Imágenes", "Images"),
    "videos": (("mp4", "mkv", "mov", "avi", "wmv", "webm", "m4v", "flv", "mpg", "mpeg", "3gp", "mts"), "Videos", "Videos"),
    "audio": (("mp3", "wav", "flac", "aac", "ogg", "m4a", "wma", "opus", "aiff"), "Audio", "Audio"),
    "code": (("py", "js", "ts", "json", "xml", "html", "htm", "css", "sql", "sh", "ps1", "bat", "cmd", "java",
              "c", "cpp", "h", "cs", "go", "rs", "ipynb", "yml", "yaml", "toml", "ini", "log"), "Código", "Code"),
    "fonts": (("ttf", "otf", "woff", "woff2"), "Fuentes", "Fonts"),
    "torrents": (("torrent",), "Torrents", "Torrents"),
    "backups": (("bak", "old", "bck"), "Respaldos", "Backups"),
}
EXT_TO_CAT = {ext: cat for cat, (exts, _, _) in CATEGORIES.items() for ext in exts}
PARTIAL = {"crdownload", "part", "partial", "download", "opdownload", "tmp"}
COPY_RE = re.compile(r"^(?P<base>.+?)\s?\((?P<n>\d{1,3})\)$")  # "setup (1)" / "setup(2)"


def category_of(name):
    return EXT_TO_CAT.get(ext_of(name), "other")


def folder_name(cat, lang):
    if cat == "other":
        return "Otros" if lang == "es" else "Other"
    _, es, en = CATEGORIES[cat]
    return es if lang == "es" else en


def all_folder_names():
    names = {"otros", "other"}
    for _, es, en in CATEGORIES.values():
        names.update((es.lower(), en.lower()))
    return names


_PLANS = {}


def _store_plan(kind, root, moves):
    plan_id = uuid.uuid4().hex[:10]
    _PLANS[plan_id] = {"kind": kind, "root": root, "moves": moves}
    for old in list(_PLANS)[:-5]:
        del _PLANS[old]
    return plan_id


# ---------------------------------------------------------------- Downloads

def analyze_downloads(job, folder, lang="es", installer_days=14, old_days=90):
    now = time.time()
    files, subdirs = [], []
    with os.scandir(folder) as it:
        for e in it:
            try:
                if e.is_dir(follow_symlinks=False):
                    subdirs.append(e.name)
                elif e.is_file(follow_symlinks=False):
                    st = e.stat(follow_symlinks=False)
                    files.append({"name": e.name, "path": e.path, "size": st.st_size, "mtime": st.st_mtime,
                                  "age": int((now - st.st_mtime) // DAY), "cat": category_of(e.name)})
            except OSError:
                continue
    job.update(count=len(files))
    subdir_lower = {d.lower() for d in subdirs}

    # --- removal suggestions (reason codes are translated in the UI)
    suggest = {}

    def add(f, reason, keep=None):
        if f["path"] not in suggest:
            suggest[f["path"]] = dict(f, reason=reason, keep=keep)

    for f in files:
        ext = ext_of(f["name"])
        stem = os.path.splitext(f["name"])[0]
        if ext in PARTIAL and f["age"] >= 1:
            add(f, "partial")
        elif f["cat"] == "installers" and f["age"] >= installer_days:
            add(f, "old_installer")
        elif f["cat"] == "archives" and stem.lower() in subdir_lower:
            add(f, "extracted")
        elif f["cat"] == "diskimages" and f["age"] >= old_days:
            add(f, "old_image")

    # exact duplicates inside Downloads (hash only files sharing a size)
    by_size = defaultdict(list)
    for f in files:
        if f["size"] > 0:
            by_size[f["size"]].append(f)
    for same in by_size.values():
        if len(same) < 2:
            continue
        by_hash = defaultdict(list)
        for f in same:
            job.check()
            job.update(current=f["name"])
            try:
                digest = _full_hash(f["path"], job)
            except OSError:
                continue
            by_hash[digest].append(f)
        for group in by_hash.values():
            if len(group) < 2:
                continue
            # keep the copy without "(1)" in its name, otherwise the oldest one
            group.sort(key=lambda f: (bool(COPY_RE.match(os.path.splitext(f["name"])[0])), f["mtime"]))
            keeper = group[0]
            for f in group[1:]:
                suggest.pop(f["path"], None)
                add(f, "duplicate", keep=keeper["name"])

    for f in files:
        if f["size"] >= 100 * 1024 * 1024 and f["age"] >= old_days:
            add(f, "big_old")

    # --- organize plan: loose files -> category folders
    moves = []
    for f in files:
        if ext_of(f["name"]) in PARTIAL:
            continue  # may still be downloading
        dest_dir = os.path.join(folder, folder_name(f["cat"], lang))
        moves.append({"src": f["path"], "dest_dir": dest_dir, "name": f["name"], "size": f["size"],
                      "cat": f["cat"], "folder": folder_name(f["cat"], lang)})
    plan_id = _store_plan("downloads", folder, moves)

    summary = defaultdict(lambda: {"files": 0, "size": 0})
    for m in moves:
        s = summary[m["folder"]]
        s["files"] += 1
        s["size"] += m["size"]
        s["cat"] = m["cat"]
    order = {"duplicate": 0, "partial": 1, "extracted": 2, "old_installer": 3, "old_image": 4, "big_old": 5}
    suggestions = sorted(suggest.values(), key=lambda s: (order[s["reason"]], -s["size"]))
    return {
        "folder": folder,
        "files": len(files),
        "total": sum(f["size"] for f in files),
        "subdirs": len(subdirs),
        "suggestions": suggestions,
        "plan_id": plan_id,
        "plan": sorted(({"folder": k, **v} for k, v in summary.items()), key=lambda x: -x["size"]),
        "moves": moves[:3000],
    }


# ---------------------------------------------------------------- Photos / Videos by date

MEDIA = set(CATEGORIES["images"][0]) | set(CATEGORIES["videos"][0])


def exif_date(path):
    """DateTimeOriginal from a JPEG's EXIF block, without Pillow. None if absent."""
    try:
        with open(path, "rb") as fh:
            if fh.read(2) != b"\xff\xd8":
                return None
            while True:
                marker = fh.read(2)
                if len(marker) < 2 or marker[0] != 0xFF:
                    return None
                seg_len = struct.unpack(">H", fh.read(2))[0]
                if marker[1] == 0xE1:
                    data = fh.read(seg_len - 2)
                    break
                if marker[1] in (0xDA, 0xD9):
                    return None
                fh.seek(seg_len - 2, os.SEEK_CUR)
    except (OSError, struct.error):
        return None
    if not data.startswith(b"Exif\0\0"):
        return None
    tiff = data[6:]
    endian = "<" if tiff[:2] == b"II" else ">"

    def ifd_entries(offset):
        try:
            (n,) = struct.unpack_from(endian + "H", tiff, offset)
            for i in range(n):
                yield struct.unpack_from(endian + "HHII", tiff, offset + 2 + i * 12)
        except struct.error:
            return

    try:
        (ifd0,) = struct.unpack_from(endian + "I", tiff, 4)
    except struct.error:
        return None
    exif_ifd = None
    fallback = None
    for tag, _typ, _cnt, val in ifd_entries(ifd0):
        if tag == 0x8769:
            exif_ifd = val
        elif tag == 0x0132:
            fallback = val
    for tag, _typ, _cnt, val in ifd_entries(exif_ifd) if exif_ifd else []:
        if tag == 0x9003:
            fallback = val
            break
    if fallback is None:
        return None
    raw = tiff[fallback:fallback + 19].decode("ascii", "ignore")
    try:
        return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


_YEAR_DIR = re.compile(r"^(19|20)\d\d$")


def plan_media_by_date(job, folder, lang="es"):
    """Loose photos/videos in `folder` -> folder/YYYY/YYYY-MM. Files already inside year folders stay."""
    moves = []
    with os.scandir(folder) as it:
        entries = [e for e in it if e.is_file(follow_symlinks=False) and ext_of(e.name) in MEDIA]
    for i, e in enumerate(entries, 1):
        if i % 50 == 0:
            job.check()
            job.update(current=e.name, progress=i / len(entries))
        st = e.stat(follow_symlinks=False)
        taken = exif_date(e.path) if ext_of(e.name) in ("jpg", "jpeg") else None
        when = taken or datetime.fromtimestamp(st.st_mtime)
        dest_dir = os.path.join(folder, f"{when:%Y}", f"{when:%Y-%m}")
        moves.append({"src": e.path, "dest_dir": dest_dir, "name": e.name, "size": st.st_size,
                      "folder": f"{when:%Y}\\{when:%Y-%m}", "source": "exif" if taken else "mtime"})
    plan_id = _store_plan("media", folder, moves)
    summary = defaultdict(lambda: {"files": 0, "size": 0})
    for m in moves:
        summary[m["folder"]]["files"] += 1
        summary[m["folder"]]["size"] += m["size"]
    return {"folder": folder, "plan_id": plan_id, "files": len(moves),
            "exif": sum(1 for m in moves if m["source"] == "exif"),
            "plan": sorted(({"folder": k, **v} for k, v in summary.items()), key=lambda x: x["folder"]),
            "moves": moves[:3000]}


# ---------------------------------------------------------------- apply / undo

def _undo_dir():
    path = os.path.join(fsutil.app_data_dir(), "undo")
    os.makedirs(path, exist_ok=True)
    return path


def apply_plan(job, plan_id, exclude=()):
    plan = _PLANS.get(plan_id)
    if not plan:
        raise KeyError("El plan expiró; vuelve a analizar / plan expired, analyze again")
    exclude = set(exclude)
    # Files deleted since the analysis (e.g. from the suggestions list) are simply skipped.
    moves = [m for m in plan["moves"] if m["src"] not in exclude and os.path.exists(m["src"])]
    done, failed = [], []
    log_path = os.path.join(_undo_dir(), f"{time.strftime('%Y%m%d-%H%M%S')}-{plan['kind']}.json")
    log = {"kind": plan["kind"], "root": plan["root"], "time": time.time(), "moves": done}
    for i, m in enumerate(moves, 1):
        if i % 25 == 0:
            job.check()
            job.update(current=m["name"], progress=i / len(moves))
        try:
            os.makedirs(m["dest_dir"], exist_ok=True)
            target = fsutil.unique_target(os.path.join(m["dest_dir"], m["name"]))
            os.rename(m["src"], target)  # same folder tree, same drive: instant
            done.append({"from": m["src"], "to": target})
        except OSError as exc:
            failed.append({"path": m["src"], "error": str(exc)})
        if i % 200 == 0:
            fsutil.save_json(os.path.relpath(log_path, fsutil.app_data_dir()), log)
    if done:
        fsutil.save_json(os.path.relpath(log_path, fsutil.app_data_dir()), log)
    _PLANS.pop(plan_id, None)
    return {"moved": len(done), "failed": failed[:200], "undo": os.path.basename(log_path) if done else None}


def last_undo(kind=None):
    try:
        names = sorted((n for n in os.listdir(_undo_dir()) if n.endswith(".json")), reverse=True)
    except OSError:
        return None
    for n in names:
        if kind is None or n.endswith(f"-{kind}.json"):
            data = fsutil.load_json(os.path.join("undo", n), None)
            if data and data.get("moves"):
                return {"name": n, "kind": data["kind"], "root": data["root"], "time": data["time"], "files": len(data["moves"])}
    return None


def undo(job, name):
    rel = os.path.join("undo", os.path.basename(name))
    data = fsutil.load_json(rel, None)
    if not data:
        raise FileNotFoundError(name)
    restored, failed = 0, []
    created_dirs = set()
    for m in reversed(data["moves"]):
        try:
            if os.path.exists(m["from"]):
                raise FileExistsError("ya existe un archivo con ese nombre / a file with that name exists")
            os.rename(m["to"], m["from"])
            restored += 1
            created_dirs.add(os.path.dirname(m["to"]))
        except OSError as exc:
            failed.append({"path": m["to"], "error": str(exc)})
    for d in sorted(created_dirs, key=len, reverse=True):  # remove folders we created if now empty
        for p in (d, os.path.dirname(d)):
            if os.path.normcase(p) != os.path.normcase(data["root"]):
                try:
                    os.rmdir(p)
                except OSError:
                    pass
    os.replace(os.path.join(fsutil.app_data_dir(), rel), os.path.join(fsutil.app_data_dir(), rel + ".undone"))
    return {"restored": restored, "failed": failed[:200]}
