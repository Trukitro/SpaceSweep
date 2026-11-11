"""Similar photos (bursts, edited copies, resized versions) without an image library.

Windows already decodes every image format it can show in Explorer (JPEG, PNG,
HEIC with the codec, WebP, RAW with codecs...). We ask the shell for a small
thumbnail through IShellItemImageFactory, then compute a 64-bit difference hash
(dHash): shrink to 9x8 grey pixels and record whether each pixel is brighter
than its right neighbour. Similar pictures have hashes that differ in few bits.

Grouping uses the pigeonhole trick: split the hash into (threshold + 1) bands;
two hashes within `threshold` bits must agree exactly on at least one band, so
only photos sharing a band are compared.
"""

import base64
import ctypes
import os
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from . import imaging, winapi
from .fsutil import walk_files
from .scanner import ext_of

PHOTO_EXT = {"jpg", "jpeg", "png", "heic", "heif", "webp", "bmp", "gif", "tif", "tiff", "avif", "jfif"}
SKIP_DIRS = {"$recycle.bin", "system volume information", "appdata", "node_modules", ".git"}

if winapi.IS_WINDOWS:
    from ctypes import wintypes

    _ole32 = ctypes.windll.ole32
    _gdi32 = ctypes.windll.gdi32
    _user32 = ctypes.windll.user32

    class _SIZE(ctypes.Structure):
        _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]

    class _BITMAP(ctypes.Structure):
        _fields_ = [("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long), ("bmHeight", ctypes.c_long),
                    ("bmWidthBytes", ctypes.c_long), ("bmPlanes", ctypes.c_ushort), ("bmBitsPixel", ctypes.c_ushort),
                    ("bmBits", ctypes.c_void_p)]

    class _BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", ctypes.c_ushort), ("biBitCount", ctypes.c_ushort), ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                    ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]

    _IID_IShellItemImageFactory = winapi._GUID.from_string("{BCC18B79-BA16-442F-80C4-8A59C30C463B}")
    _GetImage = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, _SIZE, ctypes.c_int, ctypes.POINTER(wintypes.HBITMAP))
    _Release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
    _gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    _gdi32.GetObjectW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    _gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
                                 ctypes.c_void_p, ctypes.c_uint]
    _user32.GetDC.restype = ctypes.c_void_p
    _user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    winapi._shell32.SHCreateItemFromParsingName.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_void_p,
                                                            ctypes.POINTER(ctypes.c_void_p)]

_com = threading.local()

SIIGBF_THUMBNAILONLY = 0x08


def _com_init():
    if not getattr(_com, "ready", False):
        _ole32.CoInitializeEx(None, 0x2)  # apartment-threaded, as the shell expects
        _com.ready = True


def thumbnail(path, px=64):
    """(width, height, BGRA bytes) of the shell thumbnail, or None if Windows can't make one."""
    if not winapi.IS_WINDOWS:
        return None
    _com_init()
    factory = ctypes.c_void_p()
    if winapi._shell32.SHCreateItemFromParsingName(path, None, ctypes.byref(_IID_IShellItemImageFactory),
                                                   ctypes.byref(factory)) != 0 or not factory.value:
        return None
    vtbl = ctypes.cast(ctypes.cast(factory, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    hbm = wintypes.HBITMAP()
    try:
        if _GetImage(vtbl[3])(factory, _SIZE(px, px), SIIGBF_THUMBNAILONLY, ctypes.byref(hbm)) != 0 or not hbm.value:
            return None
        bm = _BITMAP()
        _gdi32.GetObjectW(hbm, ctypes.sizeof(bm), ctypes.byref(bm))
        w, h = bm.bmWidth, abs(bm.bmHeight)
        if w <= 0 or h <= 0:
            return None
        hdr = _BITMAPINFOHEADER(biSize=ctypes.sizeof(_BITMAPINFOHEADER), biWidth=w, biHeight=-h, biPlanes=1, biBitCount=32)
        buf = ctypes.create_string_buffer(w * h * 4)
        hdc = _user32.GetDC(None)
        try:
            lines = _gdi32.GetDIBits(hdc, hbm, 0, h, buf, ctypes.byref(hdr), 0)
        finally:
            _user32.ReleaseDC(None, hdc)
        return (w, h, buf.raw) if lines == h else None
    finally:
        if hbm.value:
            _gdi32.DeleteObject(hbm)
        _Release(vtbl[2])(factory)


def dhash(w, h, bgra):
    """64-bit difference hash from BGRA pixels of any size."""
    grey = [0.0] * (9 * 8)
    count = [0] * (9 * 8)
    alpha = bgra[3::4]
    # Opaque thumbnails come back with alpha 0 everywhere; only a mixed alpha channel means transparency.
    has_alpha = any(alpha) and not all(a == 255 for a in alpha)
    for y in range(h):
        gy = y * 8 // h
        row = y * w * 4
        for x in range(w):
            i = row + x * 4
            gx = x * 9 // w
            cell = gy * 9 + gx
            lum = bgra[i + 2] * 0.299 + bgra[i + 1] * 0.587 + bgra[i] * 0.114
            if has_alpha:  # premultiplied: put transparent areas on mid-grey instead of black
                lum += 128 * (1 - bgra[i + 3] / 255)
            grey[cell] += lum
            count[cell] += 1
    cells = [grey[i] / count[i] if count[i] else 0 for i in range(72)]
    bits = 0
    for gy in range(8):
        for gx in range(8):
            bits = (bits << 1) | (cells[gy * 9 + gx] > cells[gy * 9 + gx + 1])
    return bits


def thumb_data_uri(path, px=160):
    t = thumbnail(path, px)
    if not t:
        return None
    w, h, bgra = t
    rgba = bytearray(bgra)
    rgba[0::4], rgba[2::4] = bgra[2::4], bgra[0::4]
    rgba[3::4] = b"\xff" * (w * h)
    return "data:image/png;base64," + base64.b64encode(imaging.png(w, h, bytes(rgba))).decode()


def _bands(threshold):
    n = max(1, min(16, threshold + 1))
    widths = [64 // n + (1 if i < 64 % n else 0) for i in range(n)]
    out, shift = [], 64
    for wdt in widths:
        shift -= wdt
        out.append((shift, (1 << wdt) - 1))
    return out


def group_hashes(items, threshold):
    """items: list of (key, hash). Returns list of key groups whose members are within `threshold` bits."""
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for shift, mask in _bands(threshold):
        buckets = defaultdict(list)
        for idx, (_, h) in enumerate(items):
            buckets[(h >> shift) & mask].append(idx)
        for members in buckets.values():
            if len(members) < 2 or len(members) > 400:  # giant buckets = blank/flat images; skip
                continue
            for a in range(len(members)):
                ia = members[a]
                for b in range(a + 1, len(members)):
                    ib = members[b]
                    if find(ia) != find(ib) and bin(items[ia][1] ^ items[ib][1]).count("1") <= threshold:
                        parent[find(ib)] = find(ia)
    groups = defaultdict(list)
    for i in range(len(items)):
        groups[find(i)].append(i)
    # Union-find chains A~B~C even when A and C differ a lot; re-cluster so every
    # member is within the threshold of its cluster's seed photo.
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        clusters = []
        for i in members:
            for c in clusters:
                if bin(items[c[0]][1] ^ items[i][1]).count("1") <= threshold:
                    c.append(i)
                    break
            else:
                clusters.append([i])
        out += [[items[i][0] for i in c] for c in clusters if len(c) > 1]
    return out


def find_similar(job, folders, threshold=6, min_size=20 * 1024):
    job.update(message="listing", progress=-1)
    files, seen = {}, set()

    def prune(entry):
        return entry.name.lower() in SKIP_DIRS

    for folder in folders:
        if not os.path.isdir(folder):
            continue
        for path, size, mtime, name in walk_files(folder, job, prune):
            key = os.path.normcase(path)
            if size >= min_size and ext_of(name) in PHOTO_EXT and key not in seen:
                seen.add(key)
                files[path] = (size, mtime)
    paths = list(files)
    job.update(message="hashing", count=len(paths), progress=0)
    hashes, done = [], [0]
    lock = threading.Lock()

    def work(p):
        t = thumbnail(p, 64)
        with lock:
            done[0] += 1
            if done[0] % 25 == 0:
                job.update(progress=done[0] / max(1, len(paths)), current=os.path.basename(p))
        return (p, dhash(*t)) if t else None

    with ThreadPoolExecutor(max_workers=4) as pool:
        for i, res in enumerate(pool.map(work, paths)):
            if res:
                hashes.append(res)
            if i % 100 == 0:
                job.check()
    job.update(message="grouping", progress=-1)
    groups = []
    for keys in group_hashes(hashes, threshold):
        members = sorted(({"path": p, "size": files[p][0], "mtime": files[p][1]} for p in keys), key=lambda f: -f["size"])
        groups.append({"count": len(members), "files": members, "wasted": sum(f["size"] for f in members[1:])})
    groups.sort(key=lambda g: -g["wasted"])
    return {"folders": list(folders), "scanned": len(paths), "hashed": len(hashes), "threshold": threshold,
            "groups": groups[:1500], "total_groups": len(groups), "wasted": sum(g["wasted"] for g in groups)}
