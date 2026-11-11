"""Explorer right-click entry "Analyze with SpaceSweep" for folders and drives.

Per-user (HKCU\\Software\\Classes), so no administrator rights. On Windows 11
it appears under "Show more options" (the classic menu), like any app that
doesn't ship a packaged shell extension.
"""

import sys

from . import winapi

KEYS = {
    r"Software\Classes\Directory\shell\SpaceSweep": "%1",
    r"Software\Classes\Drive\shell\SpaceSweep": "%1",
    r"Software\Classes\Directory\Background\shell\SpaceSweep": "%V",
}
LABEL = {"es": "Analizar con SpaceSweep", "en": "Analyze with SpaceSweep"}


def command(placeholder):
    from .automation import launcher_command
    prog, args = launcher_command("open")
    return f'"{prog}" {args} "{placeholder}"', prog


def install(lang="es"):
    import winreg
    for key, placeholder in KEYS.items():
        cmd, prog = command(placeholder)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, LABEL.get(lang, LABEL["en"]))
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, sys.executable if getattr(sys, "frozen", False) else prog)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + r"\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
    return status()


def uninstall():
    import winreg
    for key in KEYS:
        for sub in (key + r"\command", key):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except OSError:
                pass
    return status()


def status():
    if not winapi.IS_WINDOWS:
        return {"installed": False}
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, next(iter(KEYS)) + r"\command") as k:
            return {"installed": True, "command": winreg.QueryValueEx(k, "")[0]}
    except OSError:
        return {"installed": False}
