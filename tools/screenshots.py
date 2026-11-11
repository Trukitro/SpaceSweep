"""Regenerate the README screenshots (docs/screenshots/*.png).

Opens the real app window, drives it through a few pages and captures the
window with PrintWindow (works for WebView2 content). Downloads and Similar
photos use generated demo files in a temp folder, never your own files.

    python tools/screenshots.py [--lang es|en] [--theme dark|light]
"""

import argparse
import ctypes
import math
import os
import shutil
import sys
import tempfile
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import webview  # noqa: E402

from spacesweep import imaging  # noqa: E402
from spacesweep.__main__ import ui_dir  # noqa: E402
from spacesweep.api import Api  # noqa: E402

OUT = os.path.join(ROOT, "docs", "screenshots")
W, H = 1280, 820


def demo_data(base):
    dl = os.path.join(base, "Downloads")
    os.makedirs(dl, exist_ok=True)
    blob = os.urandom(3 * 1024 * 1024)
    old = time.time() - 60 * 86400
    files = {"VideoEditor-Setup-4.2.exe": blob, "VideoEditor-Setup-4.2 (1).exe": blob, "report-2026.pdf": b"%PDF" * 500,
             "holiday.zip": os.urandom(800_000), "movie.mkv.crdownload": os.urandom(200_000), "notes.txt": b"x" * 300,
             "GameLauncherInstaller.msi": os.urandom(2_000_000), "photo-edit.png": os.urandom(400_000)}
    for name, data in files.items():
        p = os.path.join(dl, name)
        with open(p, "wb") as fh:
            fh.write(data)
        if name.endswith((".exe", ".msi", ".crdownload")):
            os.utime(p, (old, old))
    os.makedirs(os.path.join(dl, "holiday"), exist_ok=True)

    pics = os.path.join(base, "Pictures")
    os.makedirs(pics, exist_ok=True)

    def img(name, w, h, fn):
        px = bytearray()
        for y in range(h):
            for x in range(w):
                px += bytes(max(0, min(255, int(c))) for c in fn(x / w, y / h)) + b"\xff"
        with open(os.path.join(pics, name), "wb") as fh:
            fh.write(imaging.png(w, h, bytes(px)))

    sunset = lambda x, y: (255 - 80 * y, 120 + 100 * math.sin(3 * x) * (1 - y), 90 + 150 * y)
    sea = lambda x, y: (30 + 40 * x, 90 + 120 * y, 160 + 80 * math.cos(5 * x * y))
    img("sunset.png", 360, 240, sunset)
    img("sunset (edited).png", 360, 240, lambda x, y: tuple(c * 0.9 + 15 for c in sunset(x, y)))
    img("sunset-small.png", 180, 120, sunset)
    img("sea.png", 360, 240, sea)
    img("sea-2.png", 360, 240, lambda x, y: tuple(c + 6 for c in sea(x, y)))
    img("forest.png", 360, 240, lambda x, y: (40 + 60 * y, 120 + 90 * math.sin(9 * x), 40))
    return dl, pics


def _declare():
    """64-bit handles must not be truncated to C int."""
    u, g, vp = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.c_void_p
    u.FindWindowW.restype = vp
    u.GetClientRect.argtypes = [vp, ctypes.POINTER(wintypes.RECT)]
    u.GetDC.restype, u.GetDC.argtypes = vp, [vp]
    u.ReleaseDC.argtypes = [vp, vp]
    u.PrintWindow.argtypes = [vp, vp, ctypes.c_uint]
    u.SetForegroundWindow.argtypes = [vp]
    g.CreateCompatibleDC.restype, g.CreateCompatibleDC.argtypes = vp, [vp]
    g.CreateCompatibleBitmap.restype, g.CreateCompatibleBitmap.argtypes = vp, [vp, ctypes.c_int, ctypes.c_int]
    g.SelectObject.restype, g.SelectObject.argtypes = vp, [vp, vp]
    g.GetDIBits.argtypes = [vp, vp, ctypes.c_uint, ctypes.c_uint, vp, vp, ctypes.c_uint]
    g.DeleteObject.argtypes = [vp]
    g.DeleteDC.argtypes = [vp]


def capture(hwnd, path, js=None):
    if js:  # dialogs that open on their own (e.g. "What's new" after an update) must not cover the shot
        js("document.querySelectorAll('.modal-back').forEach(m => m.remove()); "
           "document.querySelectorAll('.toast').forEach(t => t.remove());", 0.6)
        if js("document.querySelectorAll('.modal-back').length"):
            raise RuntimeError("a dialog is still open")
    _declare()
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    w, h = rect.right, rect.bottom
    hdc = user32.GetDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(hwnd, mem, 3)  # PW_CLIENTONLY | PW_RENDERFULLCONTENT

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", ctypes.c_ushort), ("biBitCount", ctypes.c_ushort), ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32), ("a", ctypes.c_long), ("b", ctypes.c_long),
                    ("c", ctypes.c_uint32), ("d", ctypes.c_uint32)]
    hdr = BIH(biSize=ctypes.sizeof(BIH), biWidth=w, biHeight=-h, biPlanes=1, biBitCount=32)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(hdr), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    bgra = buf.raw
    rgba = bytearray(bgra)
    rgba[0::4], rgba[2::4] = bgra[2::4], bgra[0::4]
    rgba[3::4] = b"\xff" * (w * h)
    with open(path, "wb") as fh:
        fh.write(imaging.png(w, h, bytes(rgba)))
    print("saved", path, f"{w}x{h}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="es")
    ap.add_argument("--theme", default="dark")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    base = tempfile.mkdtemp(prefix="spacesweep-demo-")
    dl, pics = demo_data(base)
    api = Api()
    window = webview.create_window("SpaceSweep", os.path.join(ui_dir(), "index.html"), js_api=api, width=W, height=H)
    api._window = window

    def js(code, wait=0.0):
        result = window.evaluate_js(code)
        time.sleep(wait)
        return result

    def until(cond, timeout=180):
        end = time.time() + timeout
        while time.time() < end:
            if js(cond):
                return True
            time.sleep(0.5)
        raise TimeoutError(cond)

    def run():
        try:
            until("typeof S !== 'undefined' && S.drives && S.drives.length > 0")
            time.sleep(3)  # let boot hooks finish ("What's new" dialog, update check) before shooting
            js(f"S.lang = '{args.lang}'; S.theme = '{args.theme}'; applyTheme(); renderAll(); go('home');", 1.5)
            _declare()
            hwnd = ctypes.windll.user32.FindWindowW(None, "SpaceSweep")
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            capture(hwnd, os.path.join(OUT, "home.png"), js)

            js("go('cleanup'); cleanupScan();", 1)
            until("S.cl.result !== null")
            js("document.querySelector('.main').scrollTop = 0;", 1)
            capture(hwnd, os.path.join(OUT, "cleanup.png"), js)

            js(f"S.dl.folder = {dl!r}; S.dl.res = null; renderDownloads(); go('downloads'); downloadsScan();", 1)
            until("S.dl.res !== null")
            js("", 1)
            capture(hwnd, os.path.join(OUT, "downloads.png"), js)

            js(f"S.ph.folders = [{pics!r}]; S.ph.threshold = '8'; renderPhotos(); go('photos'); photosScan();", 1)
            until("S.ph.res !== null")
            try:
                until("!S.ph.loadingThumbs && S.ph.thumbs.size >= $$('#phBody [data-thumb]').length", 60)
            finally:
                print("photos:", js("JSON.stringify({groups: S.ph.res.groups.length, thumbs: S.ph.thumbs.size, "
                                    "ok: [...S.ph.thumbs.values()].filter(Boolean).length, imgs: $$('#phBody img').length})"))
            js("document.querySelector('#phBody').scrollIntoView();", 1)
            capture(hwnd, os.path.join(OUT, "photos.png"), js)

            js("go('auto');", 2)
            capture(hwnd, os.path.join(OUT, "automatic.png"), js)
        finally:
            window.destroy()

    webview.start(run)
    shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
