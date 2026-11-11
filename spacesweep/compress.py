"""Transparent NTFS compression ("CompactGUI"-style): free space without deleting anything.

Windows can store files compressed with the XPRESS/LZX algorithms (Windows Overlay
Filter, the same thing `compact /EXE` and CompactOS use). Programs read the files
normally; decompression happens on the fly and is cheap on modern CPUs. It suits
folders that are read a lot but rarely written: installed games, SDKs, AI runtimes.

Note: when a program rewrites a compressed file (a game update), that file is
stored uncompressed again; compressing a second time picks it up.
"""

import ctypes
import os
import re
import subprocess
import zlib

from . import winapi
from .fsutil import walk_files

ALGOS = ("XPRESS4K", "XPRESS8K", "XPRESS16K", "LZX")
# Formats that are already compressed: compressing them again gains next to nothing.
INCOMPRESSIBLE = {"zip", "7z", "rar", "gz", "xz", "zst", "bz2", "cab", "jpg", "jpeg", "png", "webp", "gif", "mp4", "mkv",
                  "webm", "mov", "avi", "mp3", "ogg", "opus", "aac", "flac", "m4a", "bk2", "usm", "wem", "bnk", "vhdx",
                  "pak", "ucas", "utoc", "dds", "ktx", "ktx2", "basis", "heic", "avif", "msi", "pdf"}


if winapi.IS_WINDOWS:
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.GetCompressedFileSizeW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
    _k32.GetCompressedFileSizeW.restype = ctypes.c_uint32


def _compressed_size(path):
    """Bytes the file really occupies on disk (smaller than its size when compressed)."""
    if not winapi.IS_WINDOWS:
        return os.path.getsize(path)
    high = ctypes.c_uint32(0)
    ctypes.set_last_error(0)
    low = _k32.GetCompressedFileSizeW(path, ctypes.byref(high))
    if low == 0xFFFFFFFF and ctypes.get_last_error():
        try:
            return os.path.getsize(path)
        except OSError:
            return 0
    return (high.value << 32) + low


def status(job, path, sample_mb=64):
    """Logical size, size on disk, and an estimate of what LZX would leave."""
    logical = on_disk = files = 0
    sample_in = sample_out = 0
    budget = sample_mb * 1024 * 1024
    candidates = []
    for p, size, _, name in walk_files(path, job):
        files += 1
        logical += size
        on_disk += _compressed_size(p)
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        candidates.append((p, size, ext))
    # Estimate the ratio by deflating evenly spread 64 KB chunks of compressible files.
    compressible = [c for c in candidates if c[2] not in INCOMPRESSIBLE and c[1] > 4096]
    incompressible_bytes = sum(c[1] for c in candidates if c[2] in INCOMPRESSIBLE or c[1] <= 4096)
    step = max(1, len(compressible) // 400)
    for p, size, _ in compressible[::step]:
        if sample_in >= budget:
            break
        try:
            with open(p, "rb") as fh:
                fh.seek(max(0, size // 2 - 32768))
                chunk = fh.read(65536)
        except OSError:
            continue
        sample_in += len(chunk)
        sample_out += len(zlib.compress(chunk, 6))
    ratio = (sample_out / sample_in) if sample_in else 1.0
    ratio = min(1.0, ratio * 1.05)  # LZX lands close to deflate; stay a bit conservative
    compressible_bytes = logical - incompressible_bytes
    estimate = int(compressible_bytes * ratio + incompressible_bytes)
    return {"path": path, "files": files, "logical": logical, "on_disk": on_disk,
            "already_saved": max(0, logical - on_disk), "estimate_on_disk": min(on_disk, estimate),
            "estimate_saving": max(0, on_disk - estimate), "ratio": round(ratio, 3)}


def _run_compact(job, args, total):
    """Run compact.exe, streaming its per-file output into job progress."""
    proc = subprocess.Popen(["compact.exe", *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="oem", errors="replace",
                            creationflags=winapi.CREATE_NO_WINDOW)
    done = 0
    tail = []
    try:
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                tail = (tail + [line])[-5:]
                if re.search(r"\[OK\]|\d+(\.\d+)? to 1", line):
                    done += 1
                    if job and done % 20 == 0:
                        job.update(progress=min(0.99, done / max(1, total)), current=line[-80:])
            if job and job.cancelled:
                proc.terminate()
                break
    finally:
        proc.stdout.close()
        proc.wait()
    return proc.returncode, "\n".join(tail)


def compress(job, path, algo="LZX"):
    if algo not in ALGOS:
        raise ValueError(algo)
    if not os.path.isdir(path):
        raise ValueError("folder not found")
    before = status(None, path, sample_mb=0)
    job.update(message="compressing", progress=0)
    rc, out = _run_compact(job, ["/C", "/S:" + path, "/EXE:" + algo, "/I", "/F"], before["files"])
    after = status(None, path, sample_mb=0)
    return {"path": path, "algo": algo, "before": before["on_disk"], "after": after["on_disk"],
            "saved": max(0, before["on_disk"] - after["on_disk"]), "returncode": rc, "output": out}


def decompress(job, path):
    before = status(None, path, sample_mb=0)
    job.update(message="decompressing", progress=0)
    rc, out = _run_compact(job, ["/U", "/S:" + path, "/EXE", "/I"], before["files"])
    after = status(None, path, sample_mb=0)
    return {"path": path, "before": before["on_disk"], "after": after["on_disk"], "returncode": rc, "output": out}


def candidates(job=None):
    """Installed games plus common heavy, rarely-written folders, with idle days when known."""
    from . import inventory
    out = []
    try:
        for g in inventory.games(job)["games"]:
            out.append({"kind": "game", "name": g["name"], "path": g["path"], "size": g["size"],
                        "idle_days": g["idle_days"], "platform": g["platform"], "drive": g["drive"]})
    except OSError:
        pass
    home = os.path.expanduser("~")
    for path, name in ((os.path.join(home, ".lmstudio", "extensions"), "LM Studio runtimes"),
                       (os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk"), "Android SDK"),
                       (os.path.join(home, ".rustup"), "Rust toolchains")):
        if os.path.isdir(path):
            from .fsutil import dir_size
            out.append({"kind": "tool", "name": name, "path": path, "size": dir_size(path)[0], "idle_days": None,
                        "platform": "", "drive": os.path.splitdrive(path)[0].upper()})
    out.sort(key=lambda c: -c["size"])
    return out
