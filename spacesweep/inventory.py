"""Inventory of big installed things: programs, games, developer tools, local AI models.

Everything here is read-only discovery. Removal always goes through the owner's
own mechanism (the program's uninstaller, Steam, `docker`, `ollama rm`, `wsl`)
except for plain cache/model folders, which are deleted only on request.
"""

import glob
import json
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor

from . import winapi
from .fsutil import dir_size

DAY = 86400
HOME = os.path.expanduser("~")
LOCAL = os.environ.get("LOCALAPPDATA", os.path.join(HOME, "AppData", "Local"))
ROAM = os.environ.get("APPDATA", os.path.join(HOME, "AppData", "Roaming"))
PDATA = os.environ.get("ProgramData", r"C:\ProgramData")

if winapi.IS_WINDOWS:
    import winreg


# ================================================================ helpers

def _reg_values(root, path):
    """{name: value} of one registry key, or {} if it does not exist."""
    out = {}
    try:
        with winreg.OpenKey(root, path) as key:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                except OSError:
                    break
                out[name] = value
                i += 1
    except OSError:
        pass
    return out


def _reg_subkeys(root, path):
    try:
        with winreg.OpenKey(root, path) as key:
            n = winreg.QueryInfoKey(key)[0]
            return [winreg.EnumKey(key, i) for i in range(n)]
    except OSError:
        return []


def parse_vdf(text):
    """Valve KeyValues (.vdf/.acf) -> nested dict with lower-case keys."""
    tokens = re.findall(r'"((?:[^"\\]|\\.)*)"|([{}])', text)

    def parse(i):
        node = {}
        while i < len(tokens):
            s, brace = tokens[i]
            if brace == "}":
                return node, i + 1
            if brace == "{":  # malformed: skip
                i += 1
                continue
            i += 1
            if i >= len(tokens):
                break
            s2, brace2 = tokens[i]
            if brace2 == "{":
                value, i = parse(i + 1)
            else:
                value, i = s2.replace("\\\\", "\\"), i + 1
            node[s.lower()] = value
        return node, i

    return parse(0)[0]


def _measure_many(paths, job=None, workers=6):
    paths = [p for p in paths if p and os.path.isdir(p)]
    sizes = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for p, (size, _) in zip(paths, pool.map(lambda x: dir_size(x, job=job), paths)):
            sizes[p] = size
    return sizes


def split_command(command):
    """'"C:\\x y\\un.exe" /S' -> ('C:\\x y\\un.exe', '/S'); MsiExec /I{...} becomes /X{...} (uninstall, not repair)."""
    command = (command or "").strip()
    m = re.match(r'^"([^"]+)"\s*(.*)$', command)
    if m:
        exe, params = m.group(1), m.group(2)
    else:
        m = re.match(r"^(.*?\.exe)\s*(.*)$", command, re.I)
        exe, params = (m.group(1), m.group(2)) if m else (command, "")
    if os.path.basename(exe).lower() in ("msiexec.exe", "msiexec"):
        params = re.sub(r"(?i)/I\s*\{", "/X{", params)
    return exe, params


def launch(command):
    """Run an uninstaller command line through the shell, so it can ask for UAC itself."""
    exe, params = split_command(command)
    if not exe or not winapi.IS_WINDOWS:
        return False
    rc = winapi._shell32.ShellExecuteW(None, "open", exe, params or None, None, 1)
    return rc > 32


# ================================================================ programs

UNINSTALL = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
UNINSTALL32 = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"

# Families where several versions side by side are normal and needed.
KEEP_ALL = [
    (re.compile(r"visual c\+\+ .*redistributable|visual c\+\+ \d{4}.*runtime", re.I), "vcredist"),
    (re.compile(r"\.net (runtime|desktop runtime)|windows desktop runtime|asp\.net core .*(runtime|hosting)|\.net framework", re.I), "runtime"),
    (re.compile(r"directx|webview2|vulkan|physx|nvidia (graphics driver|hd audio|frameview|usbc)", re.I), "runtime"),
]
# Families where old versions are usually leftovers.
DEV_FAMILIES = [
    (re.compile(r"\.net sdk|microsoft \.net sdk|dotnet sdk", re.I), ".NET SDK"),
    (re.compile(r"windows software development kit", re.I), "Windows SDK"),
    (re.compile(r"^python \d\.\d+\.\d+ \(", re.I), "Python"),
    (re.compile(r"sql server management studio", re.I), "SQL Server Management Studio"),
    (re.compile(r"^node\.js", re.I), "Node.js"),
    (re.compile(r"java.*(development kit|se runtime)|jdk|openjdk|temurin", re.I), "Java"),
    (re.compile(r"android studio", re.I), "Android Studio"),
]
_NOISE = re.compile(r"\(.*?\)|\b(x64|x86|amd64|arm64|64-bit|32-bit|version|update|edition)\b|v?\d+(\.\d+)*|\b20\d\d\b", re.I)


def family_key(name):
    for rx, label in DEV_FAMILIES:
        if rx.search(name):
            return label
    key = _NOISE.sub(" ", name.lower())
    return re.sub(r"[^a-z]+", " ", key).strip()


def programs(job=None):
    if not winapi.IS_WINDOWS:
        return {"programs": [], "groups": []}
    seen, items = set(), []
    sources = [(winreg.HKEY_LOCAL_MACHINE, UNINSTALL, "machine"), (winreg.HKEY_LOCAL_MACHINE, UNINSTALL32, "machine32"),
               (winreg.HKEY_CURRENT_USER, UNINSTALL, "user")]
    for root, path, scope in sources:
        for sub in _reg_subkeys(root, path):
            v = _reg_values(root, path + "\\" + sub)
            name = (v.get("DisplayName") or "").strip()
            if not name or v.get("SystemComponent") == 1 or v.get("ParentKeyName") \
                    or str(v.get("ReleaseType", "")).lower() in ("update", "hotfix", "security update"):
                continue
            ident = (name.lower(), str(v.get("DisplayVersion", "")))
            if ident in seen:
                continue
            seen.add(ident)
            date = str(v.get("InstallDate", ""))
            items.append({
                "id": f"{scope}:{sub}", "name": name, "version": str(v.get("DisplayVersion", "") or ""),
                "publisher": str(v.get("Publisher", "") or ""),
                "installed": f"{date[:4]}-{date[4:6]}-{date[6:8]}" if re.fullmatch(r"\d{8}", date) else "",
                "size": int(v["EstimatedSize"]) * 1024 if isinstance(v.get("EstimatedSize"), int) and v["EstimatedSize"] > 0 else None,
                "location": str(v.get("InstallLocation", "") or "").strip('"'),
                "uninstall": str(v.get("UninstallString", "") or ""), "scope": scope,
            })
    if job:
        job.update(message="measuring", count=len(items))
    missing = [i["location"] for i in items if i["size"] is None and i["location"]]
    sizes = _measure_many(missing, job)
    for i in items:
        if i["size"] is None and i["location"] in sizes:
            i["size"], i["measured"] = sizes[i["location"]], True
    groups = {}
    for i in items:
        loc, unin = i["location"].lower(), i["uninstall"].lower()
        i["drive"] = os.path.splitdrive(i["location"])[0].upper() if i["location"] else ""
        i["game"] = unin.startswith("steam://") or any(k in loc for k in ("steamapps", "epic games", "xboxgames", "gog galaxy\\games"))
        if i["game"]:
            continue  # "Portal" and "Portal 2" are not two versions of one program
        known = any(rx.search(i["name"]) for rx, _ in DEV_FAMILIES)
        if known or re.search(r"\d+\.\d+|\b20\d\d\b", i["name"]) or any(rx.search(i["name"]) for rx, _ in KEEP_ALL):
            groups.setdefault(family_key(i["name"]), []).append(i)
    out_groups = []
    for key, members in groups.items():
        if len(members) < 2 or not key:
            continue
        keep = next((tag for rx, tag in KEEP_ALL if any(rx.search(m["name"]) for m in members)), None)
        members.sort(key=lambda m: [int(x) if x.isdigit() else x for x in re.split(r"[.\-]", m["version"] or "0")], reverse=True)
        out_groups.append({"family": key, "keep_all": keep, "count": len(members), "ids": [m["id"] for m in members],
                           "size": sum(m["size"] or 0 for m in members)})
        for m in members:
            m["family"] = key
            m["family_keep_all"] = keep
        if not keep:
            for m in members[1:]:
                m["older_version"] = True
    out_groups.sort(key=lambda g: (g["keep_all"] is not None, -g["size"]))
    items.sort(key=lambda i: -(i["size"] or 0))
    return {"programs": items, "groups": out_groups, "total": sum(i["size"] or 0 for i in items)}


def uninstall_program(program_id, command):
    """`command` comes from the list we returned; re-read it from the registry to be sure it is genuine."""
    scope, sub = program_id.split(":", 1)
    root, path = {"machine": (winreg.HKEY_LOCAL_MACHINE, UNINSTALL), "machine32": (winreg.HKEY_LOCAL_MACHINE, UNINSTALL32),
                  "user": (winreg.HKEY_CURRENT_USER, UNINSTALL)}[scope]
    real = _reg_values(root, path + "\\" + sub).get("UninstallString", "")
    if not real or real != command:
        raise ValueError("Uninstall command changed or missing")
    return launch(real)


# ================================================================ games

def _steam_root():
    if not winapi.IS_WINDOWS:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            return os.path.normpath(winreg.QueryValueEx(key, "SteamPath")[0])
    except OSError:
        return None


def _steam_last_played(root):
    out = {}
    for cfg in glob.glob(os.path.join(root, "userdata", "*", "config", "localconfig.vdf")):
        try:
            with open(cfg, encoding="utf-8", errors="ignore") as fh:
                data = parse_vdf(fh.read())
        except OSError:
            continue
        apps = data.get("userlocalconfigstore", {}).get("software", {}).get("valve", {}).get("steam", {}).get("apps", {})
        for appid, block in apps.items():
            if isinstance(block, dict) and block.get("lastplayed", "").isdigit():
                out[appid] = max(out.get(appid, 0), int(block["lastplayed"]))
    return out


def steam_games(root=None):
    root = root or _steam_root()
    if not root or not os.path.isdir(root):
        return []
    libs = {os.path.normcase(root): root}
    try:
        with open(os.path.join(root, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="ignore") as fh:
            for lib in parse_vdf(fh.read()).get("libraryfolders", {}).values():
                if isinstance(lib, dict) and lib.get("path"):
                    libs[os.path.normcase(lib["path"])] = lib["path"]
    except OSError:
        pass
    played = _steam_last_played(root)
    games = []
    for lib in libs.values():
        for acf in glob.glob(os.path.join(lib, "steamapps", "appmanifest_*.acf")):
            try:
                with open(acf, encoding="utf-8", errors="ignore") as fh:
                    st = parse_vdf(fh.read()).get("appstate", {})
            except OSError:
                continue
            appid = st.get("appid", "")
            if appid == "228980":  # Steamworks Common Redistributables
                continue
            last = played.get(appid) or int(st.get("lastplayed", "0") or 0) or None
            games.append({"platform": "Steam", "id": appid, "name": st.get("name", appid),
                          "path": os.path.join(lib, "steamapps", "common", st.get("installdir", "")),
                          "size": int(st.get("sizeondisk", "0") or 0), "last_played": last,
                          "uninstall": f"steam://uninstall/{appid}"})
    return games


def epic_games():
    games = []
    for item in glob.glob(os.path.join(PDATA, "Epic", "EpicGamesLauncher", "Data", "Manifests", "*.item")):
        try:
            with open(item, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        if d.get("bIsApplication") is False:
            continue
        games.append({"platform": "Epic", "id": d.get("AppName", ""), "name": d.get("DisplayName", d.get("AppName", "")),
                      "path": d.get("InstallLocation", ""), "size": int(d.get("InstallSize", 0) or 0), "last_played": None,
                      "uninstall": "com.epicgames.launcher://store/library"})
    return games


def registry_games():
    games = []
    if not winapi.IS_WINDOWS:
        return games
    hk = winreg.HKEY_LOCAL_MACHINE
    for sub in _reg_subkeys(hk, r"SOFTWARE\WOW6432Node\GOG.com\Games"):
        v = _reg_values(hk, r"SOFTWARE\WOW6432Node\GOG.com\Games" + "\\" + sub)
        if v.get("path"):
            games.append({"platform": "GOG", "id": sub, "name": v.get("gameName", sub), "path": v["path"], "size": None,
                          "last_played": None, "uninstall": v.get("uninstallCommand", "")})
    for sub in _reg_subkeys(hk, r"SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs"):
        v = _reg_values(hk, r"SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs" + "\\" + sub)
        p = (v.get("InstallDir") or "").rstrip("/\\")
        if p:
            games.append({"platform": "Ubisoft", "id": sub, "name": os.path.basename(p), "path": os.path.normpath(p),
                          "size": None, "last_played": None, "uninstall": "uplay://"})
    return games


def xbox_games():
    games = []
    for d in winapi.list_drives():
        base = os.path.join(d["root"], "XboxGames")
        if not os.path.isdir(base):
            continue
        for e in os.scandir(base):
            if e.is_dir() and e.name.lower() not in ("gamesave", "shaders", ".gamingroot"):
                games.append({"platform": "Xbox", "id": e.name, "name": e.name, "path": e.path, "size": None,
                              "last_played": None, "uninstall": "ms-settings:appsfeatures"})
    return games


def games(job=None):
    found = steam_games() + epic_games() + registry_games() + xbox_games()
    found = [g for g in found if g["path"] and os.path.isdir(g["path"])]
    sizes = _measure_many([g["path"] for g in found if not g["size"]], job)
    now = time.time()
    for g in found:
        if not g["size"]:
            g["size"] = sizes.get(g["path"], 0)
        g["drive"] = os.path.splitdrive(g["path"])[0].upper()
        g["idle_days"] = int((now - g["last_played"]) // DAY) if g["last_played"] else None
        try:
            g["installed"] = os.stat(g["path"]).st_ctime
        except OSError:
            g["installed"] = None
    found.sort(key=lambda g: -g["size"])
    return {"games": found, "total": sum(g["size"] for g in found)}


def open_uri(uri):
    if not uri or not re.match(r"^(steam|com\.epicgames\.launcher|uplay|ms-settings):", uri):
        raise ValueError("unsupported uri")
    os.startfile(uri)
    return True


def game_uninstall(platform, game_id):
    """Hand the uninstall to the game's own launcher (never delete game folders behind its back)."""
    if platform == "Steam":
        if not game_id.isdigit():
            raise ValueError("bad app id")
        return open_uri(f"steam://uninstall/{game_id}")
    if platform == "Epic":
        return open_uri("com.epicgames.launcher://store/library")
    if platform == "Ubisoft":
        return open_uri("uplay://")
    if platform == "Xbox":
        return open_uri("ms-settings:appsfeatures")
    if platform == "GOG":
        v = _reg_values(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\GOG.com\Games" + "\\" + game_id)
        return launch(v.get("uninstallCommand", ""))
    raise ValueError(platform)


# ================================================================ developer tools

def _run(args, timeout=30):
    if not shutil.which(args[0]):
        return None
    return winapi.run_hidden(args, timeout=timeout)


def docker_df():
    res = _run(["docker", "system", "df", "--format", "{{json .}}"], timeout=20)
    if res is None:
        return {"available": False}
    rc, out = res
    if rc != 0:
        return {"available": True, "running": False, "message": out.strip()[:300]}
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return {"available": True, "running": True, "rows": rows}


def docker_prune(all_images=False):
    cmds = [["docker", "builder", "prune", "-f"], ["docker", "system", "prune", "-f"] + (["-a"] if all_images else [])]
    return [{"cmd": " ".join(c), "result": (_run(c, timeout=600) or (-1, "docker not found"))} for c in cmds]


def wsl_distros():
    if not winapi.IS_WINDOWS:
        return []
    out = []
    lxss = r"Software\Microsoft\Windows\CurrentVersion\Lxss"
    for sub in _reg_subkeys(winreg.HKEY_CURRENT_USER, lxss):
        v = _reg_values(winreg.HKEY_CURRENT_USER, lxss + "\\" + sub)
        base = (v.get("BasePath") or "").replace("\\\\?\\", "")
        vhd = os.path.join(base, v.get("VhdFileName", "ext4.vhdx")) if base else ""
        out.append({"name": v.get("DistributionName", sub), "path": vhd if os.path.isfile(vhd) else base,
                    "size": os.path.getsize(vhd) if os.path.isfile(vhd) else None, "version": v.get("Version")})
    for vhd in glob.glob(os.path.join(LOCAL, "Docker", "wsl", "*", "*.vhdx")):
        if not any(os.path.normcase(d["path"]) == os.path.normcase(vhd) for d in out):
            out.append({"name": "Docker Desktop (" + os.path.basename(os.path.dirname(vhd)) + ")", "path": vhd,
                        "size": os.path.getsize(vhd), "version": 2, "docker": True})
    return out


def wsl_set_sparse(name):
    """Let the distro's virtual disk give space back to Windows automatically (WSL 2.0+)."""
    steps = [["wsl", "--terminate", name], ["wsl", "--manage", name, "--set-sparse", "true"]]
    return [{"cmd": " ".join(s), "result": (_run(s, timeout=120) or (-1, "wsl not found"))} for s in steps]


def vscode_leftovers():
    """Extension folders VS Code itself marked obsolete, or older copies of an installed extension."""
    out = []
    for flavor in (".vscode", ".vscode-insiders", ".cursor", ".windsurf"):
        ext_dir = os.path.join(HOME, flavor, "extensions")
        if not os.path.isdir(ext_dir):
            continue
        obsolete = {}
        try:
            with open(os.path.join(ext_dir, ".obsolete"), encoding="utf-8") as fh:
                obsolete = json.load(fh)
        except (OSError, ValueError):
            pass
        referenced = set()
        try:
            with open(os.path.join(ext_dir, "extensions.json"), encoding="utf-8") as fh:
                for e in json.load(fh):
                    loc = e.get("relativeLocation") or os.path.basename(e.get("location", {}).get("fsPath", ""))
                    if loc:
                        referenced.add(loc.lower())
        except (OSError, ValueError):
            referenced = None
        by_id = {}
        for d in os.scandir(ext_dir):
            if not d.is_dir():
                continue
            m = re.match(r"^(.+?)-(\d+\.\d+\.\d+.*)$", d.name)
            if m:
                by_id.setdefault(m.group(1).lower(), []).append(d)
        for ext_id, dirs in by_id.items():
            for d in dirs:
                reason = None
                if obsolete.get(d.name):
                    reason = "obsolete"
                elif referenced is not None and len(dirs) > 1 and d.name.lower() not in referenced:
                    reason = "old_version"
                if reason:
                    out.append({"tool": flavor.strip("."), "name": d.name, "path": d.path, "reason": reason,
                                "size": dir_size(d.path)[0]})
    return out


def jetbrains_leftovers():
    out = []
    rx = re.compile(r"^([A-Za-z]+?)(\d{4}\.\d+)$")
    for base, kind in ((os.path.join(ROAM, "JetBrains"), "settings"), (os.path.join(LOCAL, "JetBrains"), "caches")):
        if not os.path.isdir(base):
            continue
        by_product = {}
        for d in os.scandir(base):
            m = rx.match(d.name)
            if d.is_dir() and m:
                by_product.setdefault(m.group(1), []).append((tuple(int(x) for x in m.group(2).split(".")), d))
        for product, versions in by_product.items():
            versions.sort(reverse=True)
            for _, d in versions[1:]:
                out.append({"tool": "JetBrains", "name": d.name, "path": d.path, "kind": kind,
                            "reason": "old_version", "newest": versions[0][1].name, "size": dir_size(d.path)[0]})
    return out


def lmstudio_runtimes(base=None):
    """Old llama.cpp engines LM Studio keeps after each update. Keeps the newest of each variant
    and any version mentioned in LM Studio's own settings."""
    base = base or os.path.join(HOME, ".lmstudio")
    backends = os.path.join(base, "extensions", "backends")
    if not os.path.isdir(backends):
        return []
    in_use = ""
    for f in glob.glob(os.path.join(base, ".internal", "*.json")) + glob.glob(os.path.join(base, "settings.json")):
        name = os.path.basename(f).lower()
        if "download" in name or "index" in name or os.path.getsize(f) > 200 * 1024:
            continue  # download history / engine catalogues list every version ever seen, not the selected one
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                in_use += fh.read()
        except OSError:
            pass
    rx = re.compile(r"^(.+?)-(\d+(?:\.\d+)+)$")
    variants = {}
    for d in os.scandir(backends):
        m = rx.match(d.name)
        if d.is_dir() and m:
            variants.setdefault(m.group(1), []).append((tuple(int(x) for x in m.group(2).split(".")), d))
    out = []
    for variant, versions in variants.items():
        versions.sort(reverse=True)
        for _, d in versions[1:]:
            if d.name in in_use:
                continue
            out.append({"tool": "LM Studio", "name": d.name, "path": d.path, "reason": "old_runtime",
                        "newest": versions[0][1].name, "size": dir_size(d.path)[0]})
    return out


def build_caches():
    out = []
    for path, name in ((os.path.join(HOME, ".gradle", "caches"), "Gradle"), (os.path.join(HOME, ".m2", "repository"), "Maven"),
                       (os.path.join(LOCAL, "Yarn", "Berry", "cache"), "Yarn Berry"), (os.path.join(HOME, ".cargo", "registry"), "Cargo registry"),
                       (os.path.join(LOCAL, "pnpm", "store"), "pnpm store"), (os.path.join(HOME, "go", "pkg", "mod"), "Go modules")):
        if os.path.isdir(path):
            out.append({"tool": name, "name": name, "path": path, "reason": "cache", "size": dir_size(path)[0]})
    for avd in glob.glob(os.path.join(HOME, ".android", "avd", "*.avd")):
        out.append({"tool": "Android", "name": os.path.basename(avd)[:-4], "path": avd, "reason": "avd", "size": dir_size(avd)[0]})
    return out


def devtools(job=None):
    result = {"docker": docker_df(), "wsl": wsl_distros()}
    if job:
        job.update(message="extensions")
    result["leftovers"] = lmstudio_runtimes() + vscode_leftovers() + jetbrains_leftovers() + build_caches()
    result["leftovers"].sort(key=lambda x: -x["size"])
    return result


# ================================================================ local AI models

def _lmstudio_dirs():
    dirs = [os.path.join(HOME, ".lmstudio", "models"), os.path.join(HOME, ".cache", "lm-studio", "models")]
    try:
        with open(os.path.join(HOME, ".lmstudio", "settings.json"), encoding="utf-8") as fh:
            custom = json.load(fh).get("downloadsFolder")
        if custom:
            dirs.insert(0, custom)
    except (OSError, ValueError):
        pass
    return [d for d in dict.fromkeys(dirs) if os.path.isdir(d)]


def ai_models():
    models = []
    for base in _lmstudio_dirs():  # models/<publisher>/<repo>/*.gguf
        for repo in glob.glob(os.path.join(base, "*", "*")):
            if os.path.isdir(repo):
                files = [f for f in glob.glob(os.path.join(repo, "*")) if os.path.isfile(f)]
                if files:
                    models.append({"app": "LM Studio", "name": os.path.relpath(repo, base).replace("\\", "/"), "path": repo,
                                   "size": sum(os.path.getsize(f) for f in files),
                                   "date": max(os.path.getmtime(f) for f in files), "delete": "folder"})
    hub = os.environ.get("HF_HUB_CACHE") or os.path.join(os.environ.get("HF_HOME", os.path.join(HOME, ".cache", "huggingface")), "hub")
    for repo in glob.glob(os.path.join(hub, "models--*")) + glob.glob(os.path.join(hub, "datasets--*")):
        kind, _, rest = os.path.basename(repo).partition("--")
        models.append({"app": "Hugging Face", "name": rest.replace("--", "/") + ("" if kind == "models" else " (dataset)"),
                       "path": repo, "size": dir_size(repo)[0], "date": os.path.getmtime(repo), "delete": "folder"})
    ollama_dir = os.environ.get("OLLAMA_MODELS") or os.path.join(HOME, ".ollama", "models")
    manifests = os.path.join(ollama_dir, "manifests")
    for path in glob.glob(os.path.join(manifests, "*", "*", "*", "*")):
        try:
            with open(path, encoding="utf-8") as fh:
                m = json.load(fh)
        except (OSError, ValueError):
            continue
        parts = os.path.relpath(path, manifests).split(os.sep)
        name = (parts[2] if parts[1] == "library" else parts[1] + "/" + parts[2]) + ":" + parts[3]
        size = sum(int(layer.get("size", 0)) for layer in m.get("layers", []))
        models.append({"app": "Ollama", "name": name, "path": ollama_dir, "size": size, "date": os.path.getmtime(path),
                       "delete": "ollama" if shutil.which("ollama") else "none"})
    models.sort(key=lambda m: -m["size"])
    return {"models": models, "total": sum(m["size"] for m in models)}


def ollama_rm(name):
    if not re.fullmatch(r"[\w./:-]+", name):
        raise ValueError("bad model name")
    res = _run(["ollama", "rm", name], timeout=120)
    return res if res else (-1, "ollama not found")
