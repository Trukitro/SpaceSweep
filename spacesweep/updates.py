"""New-version check against GitHub Releases, plus the bundled changelog.

At most one request a day (cached in settings). Only the public release
metadata is fetched; nothing about the PC is sent.
"""

import json
import os
import re
import time
import urllib.request

from . import __version__, fsutil

REPO = "Trukitro/SpaceSweep"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES = f"https://github.com/{REPO}/releases"
CHANGELOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CHANGELOG.md")


def parse_version(text):
    nums = re.findall(r"\d+", text or "")[:3]
    return tuple(int(n) for n in nums) + (0,) * (3 - len(nums))


def check(force=False, opener=urllib.request.urlopen):
    settings = fsutil.load_json("settings.json", {})
    if settings.get("check_updates") is False and not force:
        return {"current": __version__, "enabled": False}
    cache = settings.get("update_cache") or {}
    if not force and time.time() - cache.get("time", 0) < 86400 and cache.get("tag"):
        data = cache
    else:
        req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json", "User-Agent": f"SpaceSweep/{__version__}"})
        try:
            with opener(req, timeout=6) as resp:
                rel = json.loads(resp.read().decode("utf-8"))
        except (OSError, ValueError) as exc:
            return {"current": __version__, "enabled": True, "error": str(exc)}
        assets = {a.get("name"): a.get("browser_download_url") for a in rel.get("assets", [])}
        data = {"time": time.time(), "tag": rel.get("tag_name", ""), "url": rel.get("html_url", RELEASES),
                "notes": (rel.get("body") or "")[:4000], "setup": assets.get("SpaceSweepSetup.exe"),
                "portable": assets.get("SpaceSweep.exe")}
        settings = fsutil.load_json("settings.json", {})
        settings["update_cache"] = data
        fsutil.save_json("settings.json", settings)
    return {"current": __version__, "enabled": True, "latest": data["tag"].lstrip("v"), "url": data["url"],
            "notes": data["notes"], "setup": data.get("setup"), "portable": data.get("portable"),
            "newer": parse_version(data["tag"]) > parse_version(__version__)}


def changelog():
    try:
        with open(CHANGELOG, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def whats_new():
    """Changelog text if this version hasn't been shown yet (marks it as seen)."""
    settings = fsutil.load_json("settings.json", {})
    seen = settings.get("last_seen_version")
    settings["last_seen_version"] = __version__
    fsutil.save_json("settings.json", settings)
    if seen is None or parse_version(seen) >= parse_version(__version__):
        return None  # first run ever, or nothing new
    return {"from": seen, "to": __version__}
