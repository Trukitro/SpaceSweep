"""Thin ctypes wrappers around the Windows APIs SpaceSweep needs.

Using ctypes instead of pywin32 keeps the app dependency-free (and the
packaged .exe small). Every function degrades gracefully off Windows so the
pure-Python parts can still be tested anywhere.
"""

import ctypes
import os
import shutil
import string
import subprocess
import sys
import uuid

IS_WINDOWS = os.name == "nt"
CREATE_NO_WINDOW = 0x08000000

if IS_WINDOWS:
    from ctypes import wintypes

    _shell32 = ctypes.windll.shell32
    _kernel32 = ctypes.windll.kernel32
    _ole32 = ctypes.windll.ole32

# Natural alignment on 64-bit; shellapi.h packs these structs to 1 on 32-bit.
_PACK = 1 if ctypes.sizeof(ctypes.c_void_p) == 4 else 8


# ---------------------------------------------------------------- admin

def is_admin():
    if not IS_WINDOWS:
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False
    try:
        return bool(_shell32.IsUserAnAdmin())
    except OSError:
        return False


def relaunch_as_admin():
    """Start a second, elevated copy of the app (UAC prompt). Returns True if launched."""
    if not IS_WINDOWS:
        return False
    if getattr(sys, "frozen", False):
        exe, params, cwd = sys.executable, subprocess.list2cmdline(sys.argv[1:]), None
    else:
        exe = sys.executable
        params = subprocess.list2cmdline(["-m", "spacesweep", *sys.argv[1:]])
        cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rc = _shell32.ShellExecuteW(None, "runas", exe, params, cwd, 1)
    return rc > 32


# ---------------------------------------------------------------- drives

_DRIVE_TYPES = {2: "removable", 3: "fixed", 4: "network", 5: "cdrom", 6: "ramdisk"}


def list_drives():
    drives = []
    letters = []
    if IS_WINDOWS:
        mask = _kernel32.GetLogicalDrives()
        letters = [c for i, c in enumerate(string.ascii_uppercase) if mask >> i & 1]
    else:
        letters = ["/"]
    system_drive = os.environ.get("SystemDrive", "C:").rstrip("\\").upper()
    for letter in letters:
        root = f"{letter}:\\" if IS_WINDOWS else letter
        kind, label, fs = "fixed", "", ""
        if IS_WINDOWS:
            kind = _DRIVE_TYPES.get(_kernel32.GetDriveTypeW(root), "unknown")
            if kind == "cdrom":
                continue
            name_buf = ctypes.create_unicode_buffer(261)
            fs_buf = ctypes.create_unicode_buffer(261)
            if _kernel32.GetVolumeInformationW(root, name_buf, 261, None, None, None, fs_buf, 261):
                label, fs = name_buf.value, fs_buf.value
        try:
            usage = shutil.disk_usage(root)
        except OSError:
            continue  # empty card reader, disconnected network share, ...
        drives.append({
            "root": root,
            "letter": letter if IS_WINDOWS else "/",
            "label": label,
            "fs": fs,
            "type": kind,
            "system": IS_WINDOWS and f"{letter}:" == system_drive,
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
        })
    return drives


def disk_free(root):
    try:
        return shutil.disk_usage(root).free
    except OSError:
        return 0


# ---------------------------------------------------------------- known folders

_KNOWN_FOLDERS = {
    "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
    "videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
    "music": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
    "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
}


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def from_string(cls, text):
        raw = uuid.UUID(text).bytes_le
        g = cls()
        ctypes.memmove(ctypes.byref(g), raw, 16)
        return g


def known_folder(name):
    """Real location of Downloads, Documents, ... (respects OneDrive/folder redirection)."""
    fallback = os.path.join(os.path.expanduser("~"), name.capitalize())
    if not IS_WINDOWS or name not in _KNOWN_FOLDERS:
        return fallback
    path_ptr = ctypes.c_wchar_p()
    guid = _GUID.from_string(_KNOWN_FOLDERS[name])
    hr = _shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(path_ptr))
    if hr != 0:
        return fallback
    try:
        return path_ptr.value
    finally:
        _ole32.CoTaskMemFree(path_ptr)


def user_folders():
    return {name: known_folder(name) for name in _KNOWN_FOLDERS}


# ---------------------------------------------------------------- recycle bin

class _SHQUERYRBINFO(ctypes.Structure):
    _pack_ = _PACK
    _fields_ = [("cbSize", ctypes.c_uint32), ("i64Size", ctypes.c_int64), ("i64NumItems", ctypes.c_int64)]


def recycle_bin_info(root=None):
    """(bytes, items) in the Recycle Bin of one drive, or of all drives when root is None."""
    if not IS_WINDOWS:
        return 0, 0
    info = _SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(_SHQUERYRBINFO)
    if _shell32.SHQueryRecycleBinW(root, ctypes.byref(info)) != 0:
        return 0, 0
    return info.i64Size, info.i64NumItems


def empty_recycle_bin(root=None):
    if not IS_WINDOWS:
        return False
    flags = 0x1 | 0x2 | 0x4  # no confirmation, no progress UI, no sound
    hr = _shell32.SHEmptyRecycleBinW(None, root, flags)
    return hr in (0, -2147418113)  # S_OK, or E_UNEXPECTED when it was already empty


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _pack_ = _PACK
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("wFunc", ctypes.c_uint),
        ("pFrom", ctypes.c_wchar_p),
        ("pTo", ctypes.c_wchar_p),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", ctypes.c_int),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", ctypes.c_wchar_p),
    ]


_FO_DELETE = 3
_FOF_SILENT = 0x4
_FOF_NOCONFIRMATION = 0x10
_FOF_ALLOWUNDO = 0x40
_FOF_NOERRORUI = 0x400


def send_to_recycle_bin(paths):
    """Move files/folders to the Recycle Bin. Returns True when the shell reported success."""
    paths = [os.path.abspath(p) for p in paths if p]
    if not paths:
        return True
    if not IS_WINDOWS:
        raise OSError("Recycle Bin is only available on Windows")
    buf = ctypes.create_unicode_buffer("\0".join(paths) + "\0")  # double-null terminated
    op = _SHFILEOPSTRUCTW()
    op.wFunc = _FO_DELETE
    op.pFrom = ctypes.cast(buf, ctypes.c_wchar_p)
    op.fFlags = _FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_SILENT | _FOF_NOERRORUI
    rc = _shell32.SHFileOperationW(ctypes.byref(op))
    return rc == 0 and not op.fAnyOperationsAborted


# ---------------------------------------------------------------- shell helpers

def open_in_explorer(path):
    if not path or not os.path.exists(path):
        return False
    if not IS_WINDOWS:
        subprocess.Popen(["xdg-open", path if os.path.isdir(path) else os.path.dirname(path)])
        return True
    if os.path.isdir(path):
        os.startfile(path)
    else:
        subprocess.Popen(["explorer.exe", "/select,", os.path.normpath(path)])
    return True


# Windows tools the UI can open for things SpaceSweep deliberately does not do itself.
TOOLS = {
    "cleanmgr": ["cleanmgr.exe"],
    "storage": "ms-settings:storagesense",
    "apps": "ms-settings:appsfeatures",
    "protection": ["SystemPropertiesProtection.exe"],
    "performance": ["SystemPropertiesPerformance.exe"],
}


def open_tool(name):
    target = TOOLS.get(name)
    if not target or not IS_WINDOWS:
        return False
    if isinstance(target, str):
        os.startfile(target)
    else:
        subprocess.Popen(target, creationflags=CREATE_NO_WINDOW)
    return True


def running_processes():
    """Lower-case image names of running processes (used to warn 'close Chrome first')."""
    if not IS_WINDOWS:
        return set()
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                             creationflags=CREATE_NO_WINDOW, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    names = set()
    for line in out.splitlines():
        if line.startswith('"'):
            names.add(line.split('","', 1)[0].strip('"').lower())
    return names


def run_hidden(args, timeout=120):
    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                             creationflags=CREATE_NO_WINDOW if IS_WINDOWS else 0)
        return res.returncode, (res.stdout or "") + (res.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, str(exc)
