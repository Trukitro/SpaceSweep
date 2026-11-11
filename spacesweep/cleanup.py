"""Cleanup catalogue: what can be deleted, why, and what happens if you do.

Every rule explains itself in Spanish and English. Groups:
  safe    - caches and leftovers Windows/apps rebuild on their own.
  review  - safe for the PC, but you lose something (downloads, deleted files,
            a slower first game launch). Unchecked by default.
  space   - big things SpaceSweep only points at (WSL disks, AI models...).
  system  - Windows features you change in Windows itself (page file, ...).
  never   - folders people delete by hand and break Windows. Explained, never touched.
"""

import glob
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import fsutil, winapi

E = os.environ
LOCAL = E.get("LOCALAPPDATA", "")
ROAM = E.get("APPDATA", "")
PDATA = E.get("ProgramData", r"C:\ProgramData")
WIN = E.get("SystemRoot", r"C:\Windows")
SYS = E.get("SystemDrive", "C:") + "\\"
HOME = os.path.expanduser("~")


def T(es, en):
    return {"es": es, "en": en}


def _steam_shadercache():
    roots = []
    if winapi.IS_WINDOWS:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                roots.append(winreg.QueryValueEx(key, "SteamPath")[0])
        except OSError:
            pass
    libs = set(roots)
    for r in roots:
        try:
            with open(os.path.join(r, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="ignore") as fh:
                libs.update(m.replace("\\\\", "\\") for m in re.findall(r'"path"\s+"([^"]+)"', fh.read()))
        except OSError:
            pass
    return [os.path.join(lib, "steamapps", "shadercache") for lib in libs]


def _browser_caches():
    pats = []
    for base in (r"Google\Chrome", r"Microsoft\Edge", r"BraveSoftware\Brave-Browser", r"Vivaldi"):
        for sub in ("Cache", "Code Cache", "GPUCache"):
            pats.append(os.path.join(LOCAL, base, "User Data", "*", sub))
    pats += [os.path.join(LOCAL, "Opera Software", "*", "Cache"),
             os.path.join(LOCAL, "Mozilla", "Firefox", "Profiles", "*", "cache2")]
    return pats


RULES = [
    # ------------------------------------------------------------ safe
    dict(id="user_temp", group="safe", icon="temp",
         name=T("Archivos temporales de tu usuario", "Your temporary files"),
         what=T("Archivos que los programas dejan en %TEMP% mientras instalan o trabajan.",
                "Files programs leave in %TEMP% while installing or working."),
         effect=T("Nada. Solo se borran los de más de 1 día; los que estén en uso se saltan.",
                  "Nothing. Only files older than 1 day; files in use are skipped."),
         paths=[E.get("TEMP", os.path.join(LOCAL, "Temp"))], older=1),
    dict(id="win_temp", group="safe", icon="temp", admin=True,
         name=T("Temporales de Windows", "Windows temporary files"),
         what=T("La carpeta Temp del sistema (C:\\Windows\\Temp).", "The system Temp folder (C:\\Windows\\Temp)."),
         effect=T("Nada. Solo los de más de 1 día.", "Nothing. Only files older than 1 day."),
         paths=[os.path.join(WIN, "Temp")], older=1),
    dict(id="nvidia_shader", group="safe", icon="gpu",
         name=T("Caché de shaders de NVIDIA", "NVIDIA shader cache"),
         what=T("Shaders compilados por el driver para tus juegos (los archivos .nvph). Crece sin límite.",
                "Shaders the driver compiled for your games (.nvph files). Grows without limit."),
         effect=T("Los juegos lo reconstruyen solos; puede haber algo de tirón la primera vez que abras cada juego.",
                  "Games rebuild it; expect a little stutter the first time you open each game."),
         paths=[os.path.join(LOCAL, "NVIDIA", "DXCache"), os.path.join(LOCAL, "NVIDIA", "GLCache"),
                os.path.join(E.get("USERPROFILE", HOME), "AppData", "LocalLow", "NVIDIA", "PerDriverVersion", "DXCache")]),
    dict(id="amd_intel_shader", group="safe", icon="gpu",
         name=T("Caché de shaders de AMD / Intel / DirectX", "AMD / Intel / DirectX shader cache"),
         what=T("Lo mismo que el de NVIDIA, para otras tarjetas y para DirectX.",
                "Same idea as NVIDIA's, for other GPUs and for DirectX itself."),
         effect=T("Se reconstruye solo al jugar.", "Rebuilt automatically when you play."),
         paths=[os.path.join(LOCAL, "AMD", "DxCache"), os.path.join(LOCAL, "AMD", "DxcCache"),
                os.path.join(LOCAL, "AMD", "GLCache"), os.path.join(LOCAL, "AMD", "VkCache"),
                os.path.join(LOCAL, "Intel", "ShaderCache"), os.path.join(LOCAL, "D3DSCache")]),
    dict(id="driver_installers", group="safe", icon="driver",
         name=T("Instaladores de drivers ya usados", "Used driver installers"),
         what=T("Drivers que la app de NVIDIA/AMD descargó y descomprimió (C:\\NVIDIA, C:\\AMD, ota-artifacts).",
                "Drivers the NVIDIA/AMD app downloaded and unpacked (C:\\NVIDIA, C:\\AMD, ota-artifacts)."),
         effect=T("Nada: el driver ya está instalado. Si algún día lo reinstalas, se descarga de nuevo.",
                  "Nothing: the driver is already installed. A reinstall downloads it again."),
         paths=[os.path.join(PDATA, "NVIDIA Corporation", "NVIDIA app", "UpdateFramework", "ota-artifacts"),
                os.path.join(PDATA, "NVIDIA Corporation", "Downloader"),
                os.path.join(SYS, "NVIDIA"), os.path.join(SYS, "AMD")]),
    dict(id="update_cache", group="safe", icon="update", admin=True, services=["wuauserv", "bits"],
         name=T("Descargas de Windows Update", "Windows Update downloads"),
         what=T("Paquetes de actualizaciones que Windows ya descargó (SoftwareDistribution\\Download).",
                "Update packages Windows already downloaded (SoftwareDistribution\\Download)."),
         effect=T("Nada. Si alguna actualización estaba pendiente, Windows la vuelve a bajar.",
                  "Nothing. A pending update is simply downloaded again."),
         paths=[os.path.join(WIN, "SoftwareDistribution", "Download")]),
    dict(id="delivery_opt", group="safe", icon="update", admin=True, services=["dosvc"],
         name=T("Caché de Optimización de entrega", "Delivery Optimization cache"),
         what=T("Copias de actualizaciones que Windows comparte con otras PCs.",
                "Update copies Windows shares with other PCs."),
         effect=T("Nada.", "Nothing."),
         paths=[os.path.join(WIN, "ServiceProfiles", "NetworkService", "AppData", "Local", "Microsoft",
                             "Windows", "DeliveryOptimization", "Cache")]),
    dict(id="crash_dumps", group="safe", icon="bug",
         name=T("Volcados de errores y reportes", "Crash dumps and error reports"),
         what=T("Copias de memoria que se guardan cuando un programa o Windows se cae, y reportes de error.",
                "Memory copies saved when a program or Windows crashes, plus error reports."),
         effect=T("Nada, salvo que un técnico te pidiera un volcado para diagnosticar un fallo.",
                  "Nothing, unless a technician asked you for a dump to diagnose a crash."),
         paths=[os.path.join(LOCAL, "CrashDumps"), os.path.join(PDATA, "Microsoft", "Windows", "WER", "ReportArchive"),
                os.path.join(PDATA, "Microsoft", "Windows", "WER", "ReportQueue"), os.path.join(LOCAL, "Microsoft", "Windows", "WER"),
                os.path.join(WIN, "Minidump"), os.path.join(WIN, "LiveKernelReports"), os.path.join(WIN, "MEMORY.DMP")]),
    dict(id="thumbs", group="safe", icon="image",
         name=T("Caché de miniaturas", "Thumbnail cache"),
         what=T("Las vistas previas de fotos y videos que muestra el Explorador.",
                "The photo/video previews File Explorer shows."),
         effect=T("El Explorador las vuelve a crear al abrir cada carpeta (un poco más lento la primera vez).",
                  "Explorer recreates them when you open each folder (slightly slower the first time)."),
         paths=[os.path.join(LOCAL, "Microsoft", "Windows", "Explorer", "thumbcache_*.db")]),
    dict(id="browser_cache", group="safe", icon="globe", close=["chrome.exe", "msedge.exe", "brave.exe", "opera.exe", "firefox.exe", "vivaldi.exe"],
         name=T("Caché de navegadores", "Browser caches"),
         what=T("Copias de páginas e imágenes de Chrome, Edge, Brave, Opera, Firefox y Vivaldi. No toca contraseñas, historial ni sesiones.",
                "Saved copies of pages and images from Chrome, Edge, Brave, Opera, Firefox and Vivaldi. Passwords, history and logins are not touched."),
         effect=T("Las páginas cargan un poco más lento la primera vez. Cierra el navegador para liberar todo.",
                  "Pages load a bit slower the first time. Close the browser to free everything."),
         paths=_browser_caches()),
    dict(id="app_cache", group="safe", icon="app", close=["code.exe", "discord.exe"],
         name=T("Caché de VS Code y Discord", "VS Code and Discord caches"),
         what=T("Cachés internas y extensiones .vsix ya instaladas de VS Code; caché de Discord.",
                "Internal caches and already-installed .vsix extension packages of VS Code; Discord's cache."),
         effect=T("Nada; se regeneran.", "Nothing; they are regenerated."),
         paths=[os.path.join(ROAM, "Code", d) for d in ("Cache", "CachedData", "CachedExtensionVSIXs", "Code Cache", "GPUCache", "logs")]
               + [os.path.join(ROAM, "discord", d) for d in ("Cache", "Code Cache", "GPUCache")]),
    dict(id="dev_cache", group="safe", icon="code",
         name=T("Cachés de programación (pip, npm, yarn, uv, NuGet, Go)", "Developer caches (pip, npm, yarn, uv, NuGet, Go)"),
         what=T("Paquetes que estas herramientas guardan por si los vuelves a instalar.",
                "Packages these tools keep in case you install them again."),
         effect=T("Nada en tus proyectos. La próxima instalación descarga los paquetes otra vez.",
                  "Nothing in your projects. The next install downloads the packages again."),
         paths=[os.path.join(LOCAL, "pip", "cache"), os.path.join(LOCAL, "npm-cache"), os.path.join(ROAM, "npm-cache"),
                os.path.join(LOCAL, "Yarn", "Cache"), os.path.join(LOCAL, "uv", "cache"), os.path.join(LOCAL, "NuGet", "v3-cache"),
                os.path.join(LOCAL, "NuGet", "plugins-cache"), os.path.join(LOCAL, "go-build"),
                os.path.join(LOCAL, "SquirrelTemp")]),
    # ------------------------------------------------------------ review
    dict(id="recycle_bin", group="review", icon="trash", mode="recyclebin",
         name=T("Papelera de reciclaje", "Recycle Bin"),
         what=T("Archivos que tú borraste. Siguen ocupando espacio hasta que vacías la papelera.",
                "Files you deleted. They keep using space until the bin is emptied."),
         effect=T("Ya no podrás recuperarlos. Revisa la papelera antes si no estás seguro.",
                  "You can no longer restore them. Look inside first if unsure."),
         paths=[]),
    dict(id="game_shaders", group="review", icon="game",
         name=T("Shaders precompilados de juegos (Steam / Xbox)", "Pre-compiled game shaders (Steam / Xbox)"),
         what=T("Shaders que Steam o la app Xbox descargan para que los juegos abran sin tirones.",
                "Shaders Steam or the Xbox app download so games start without stutter."),
         effect=T("Se vuelven a descargar o compilar; la próxima vez que abras el juego tarda más en cargar.",
                  "Downloaded or compiled again; the game takes longer to load next time."),
         paths=_steam_shadercache() + [os.path.join(SYS, "XboxGames", "Shaders")]),
    dict(id="android_images", group="review", icon="phone",
         name=T("Imágenes del emulador de Android", "Android emulator images"),
         what=T("Sistemas Android descargados por Android Studio para el emulador.",
                "Android system images Android Studio downloaded for the emulator."),
         effect=T("Tus teléfonos virtuales pedirán descargar la imagen otra vez. Tus proyectos no se tocan.",
                  "Your virtual phones will ask to download the image again. Projects are untouched."),
         paths=[os.path.join(LOCAL, "Android", "Sdk", "system-images")]),
    dict(id="unity_downloads", group="review", icon="download",
         name=T("Instaladores descargados por Unity Hub", "Installers downloaded by Unity Hub"),
         what=T("Instaladores de versiones de Unity que Unity Hub dejó tras instalar.",
                "Unity version installers Unity Hub left behind after installing."),
         effect=T("Nada si la instalación ya terminó.", "Nothing if the installation already finished."),
         paths=[os.path.join(LOCAL, "Packages", "UnityTechnologies.UnityHub_*", "LocalCache", "Roaming", "UnityHub", "downloads"),
                os.path.join(ROAM, "UnityHub", "downloads")]),
    dict(id="spotify_cache", group="review", icon="music", close=["spotify.exe"],
         name=T("Caché de Spotify", "Spotify cache"),
         what=T("Canciones que Spotify guardó mientras las escuchabas (no tus descargas offline).",
                "Songs Spotify cached while you listened (not your offline downloads)."),
         effect=T("Las canciones se vuelven a cargar de internet.", "Songs stream from the internet again."),
         paths=[os.path.join(LOCAL, "Spotify", "Data")]),
    # ------------------------------------------------------------ space (pointers only)
    dict(id="wsl_disks", group="space", icon="disk", mode="info",
         name=T("Discos de WSL (Linux) y Docker", "WSL (Linux) and Docker disks"),
         what=T("Archivos .vhdx donde vive tu Linux y tus imágenes de Docker. Crecen pero nunca se encogen solos.",
                "The .vhdx files holding your Linux and Docker images. They grow but never shrink by themselves."),
         effect=T("NO los borres: perderías Linux/Docker completo. Usa `docker system prune -a` y luego compacta el disco, o muévelos a otro disco con `wsl --manage <distro> --move <carpeta>`.",
                  "Do NOT delete them: you'd lose the whole Linux/Docker. Run `docker system prune -a` and compact the disk, or move them with `wsl --manage <distro> --move <folder>`."),
         paths=[os.path.join(LOCAL, "Packages", "*", "LocalState", "ext4.vhdx"),
                os.path.join(LOCAL, "Docker", "wsl", "disk", "docker_data.vhdx"),
                os.path.join(LOCAL, "Docker", "wsl", "data", "ext4.vhdx")]),
    dict(id="ai_models", group="space", icon="brain", mode="info",
         name=T("Modelos de IA locales", "Local AI models"),
         what=T("Modelos de LM Studio, Ollama y Hugging Face. Cada uno pesa varios GB.",
                "LM Studio, Ollama and Hugging Face models. Each is several GB."),
         effect=T("Borra los que no uses desde la propia app, o cambia su carpeta a otro disco en la configuración de la app.",
                  "Delete unused ones from the app itself, or move its models folder to another drive in the app settings."),
         paths=[os.path.join(HOME, ".lmstudio", "models"), os.path.join(HOME, ".cache", "lm-studio", "models"),
                os.path.join(HOME, ".ollama", "models"), os.path.join(HOME, ".cache", "huggingface")]),
    dict(id="old_windows", group="space", icon="windows", mode="info", tool="cleanmgr",
         name=T("Restos de actualizaciones grandes de Windows", "Leftovers of big Windows upgrades"),
         what=T("Windows.old y $WINDOWS.~BT: la versión anterior de Windows y archivos de instalación.",
                "Windows.old and $WINDOWS.~BT: the previous Windows version and setup files."),
         effect=T("Bórralos con el Liberador de espacio → «Limpiar archivos del sistema»: Windows sabe si todavía los necesita (p. ej. para volver atrás).",
                  "Remove them with Disk Cleanup → 'Clean up system files'. It knows whether they're still needed (e.g. to roll back)."),
         paths=[os.path.join(SYS, "Windows.old"), os.path.join(SYS, "$WINDOWS.~BT"), os.path.join(SYS, "$WINDOWS.~WS")]),
    # ------------------------------------------------------------ system (changed in Windows)
    dict(id="pagefile", group="system", icon="memory", mode="info", tool="performance",
         name=T("Archivo de paginación (pagefile.sys)", "Page file (pagefile.sys)"),
         what=T("Memoria virtual de Windows. Su tamaño lo decide Windows según tu RAM.",
                "Windows virtual memory. Windows sizes it based on your RAM."),
         effect=T("Con 16 GB de RAM o más puedes moverlo a otro disco: Rendimiento → Opciones avanzadas → Memoria virtual. No lo desactives del todo.",
                  "With 16 GB of RAM or more you can move it to another drive: Performance → Advanced → Virtual memory. Don't disable it entirely."),
         paths=[os.path.join(SYS, "pagefile.sys"), os.path.join(SYS, "swapfile.sys")]),
    dict(id="hiberfile", group="system", icon="moon", mode="info",
         name=T("Archivo de hibernación (hiberfil.sys)", "Hibernation file (hiberfil.sys)"),
         what=T("Guarda la memoria cuando la PC hiberna. También lo usa el «inicio rápido».",
                "Stores memory when the PC hibernates. Also used by Fast Startup."),
         effect=T("Si no hibernas, abre una terminal como administrador y ejecuta `powercfg /h off`. Perderás la hibernación y el inicio rápido.",
                  "If you never hibernate, run `powercfg /h off` in an admin terminal. You lose hibernation and Fast Startup."),
         paths=[os.path.join(SYS, "hiberfil.sys")]),
    dict(id="restore_points", group="system", icon="history", mode="shadow", tool="protection",
         name=T("Puntos de restauración", "System restore points"),
         what=T("Copias del sistema para volver atrás si algo sale mal. Están en «System Volume Information», que no se ve en el Explorador.",
                "System snapshots to roll back if something breaks. They live in 'System Volume Information', invisible in Explorer."),
         effect=T("Puedes bajar el espacio máximo (p. ej. 5%) en Protección del sistema → Configurar. No los desactives: son tu red de seguridad.",
                  "Lower the max usage (e.g. 5%) in System Protection → Configure. Don't disable them: they're your safety net."),
         paths=[]),
    # ------------------------------------------------------------ never
    dict(id="win_installer", group="never", icon="shield", mode="info",
         name=T("C:\\Windows\\Installer", "C:\\Windows\\Installer"),
         what=T("Copias de los instaladores de tus programas.", "Copies of your programs' installers."),
         effect=T("Si lo borras no podrás desinstalar ni actualizar programas.", "Deleting it breaks uninstalling and updating programs."),
         paths=[os.path.join(WIN, "Installer")]),
    dict(id="winsxs", group="never", icon="shield", mode="info", tool="cleanmgr", nosize=True,
         name=T("C:\\Windows\\WinSxS y DriverStore", "C:\\Windows\\WinSxS and DriverStore"),
         what=T("Componentes y drivers de Windows. El tamaño que muestra el Explorador está inflado: muchos archivos se cuentan dos veces.",
                "Windows components and drivers. Explorer's size is inflated: many files are counted twice."),
         effect=T("Borrar a mano rompe Windows. El Liberador de espacio (Limpiar archivos del sistema) los reduce de forma segura.",
                  "Deleting by hand breaks Windows. Disk Cleanup (Clean up system files) trims them safely."),
         paths=[os.path.join(WIN, "WinSxS")]),
]


def _resolve(rule):
    out = []
    for pattern in rule.get("paths", []):
        matches = glob.glob(pattern) if any(ch in pattern for ch in "*?[") else [pattern]
        out += [m for m in matches if os.path.exists(m)]
    seen, unique = set(), []
    for p in out:
        key = os.path.normcase(os.path.abspath(p))
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def _on_drive(path, drive_root):
    return os.path.splitdrive(os.path.abspath(path))[0].upper() == os.path.splitdrive(drive_root)[0].upper()


def _shadow_storage():
    rc, out = winapi.run_hidden(["powershell", "-NoProfile", "-Command",
                                 "(Get-CimInstance Win32_ShadowStorage | Measure-Object UsedSpace -Sum).Sum"], timeout=40)
    try:
        return int(out.strip().splitlines()[-1]) if rc == 0 and out.strip() else None
    except ValueError:
        return None


def _measure(rule, drive_root, job):
    item = {k: rule.get(k) for k in ("id", "group", "icon", "name", "what", "effect", "tool")}
    item.update(admin=rule.get("admin", False), mode=rule.get("mode", "contents"),
                close=rule.get("close", []), size=0, files=0, paths=[], measured=True)
    mode = item["mode"]
    if mode == "recyclebin":
        size, count = winapi.recycle_bin_info(drive_root)
        item.update(size=size, files=count, paths=[{"path": drive_root + "$Recycle.Bin", "size": size}])
        return item
    if mode == "shadow":
        size = _shadow_storage() if winapi.is_admin() else None
        item.update(size=size or 0, measured=size is not None)
        return item
    for p in _resolve(rule):
        if not _on_drive(p, drive_root):
            continue
        if rule.get("nosize"):
            item["paths"].append({"path": p, "size": None})
            item["measured"] = False
            continue
        size, count = fsutil.dir_size(p, rule.get("older", 0), job)
        item["paths"].append({"path": p, "size": size})
        item["size"] += size
        item["files"] += count
    return item


def scan(job, drive_root):
    job.update(message="cleanup-scan", current=drive_root)
    is_system = _on_drive(SYS, drive_root)
    rules = [r for r in RULES if is_system or r.get("mode") == "recyclebin"]
    results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_measure, r, drive_root, job): r for r in rules}
        for i, fut in enumerate(futures, 1):
            results.append(fut.result())
            job.update(progress=i / len(futures), current=futures[fut]["name"]["es"])
    order = {r["id"]: i for i, r in enumerate(RULES)}
    results.sort(key=lambda r: order[r["id"]])
    for r in results:
        r["exists"] = bool(r["paths"]) or r["mode"] in ("recyclebin", "shadow")
    running = winapi.running_processes()
    for r in results:
        r["running"] = sorted(p for p in r["close"] if p in running)
    try:
        from . import history
        history.save_rule_sizes(drive_root, results)
        growth = history.rule_growth(drive_root)
    except OSError:
        growth = {"since": None, "items": []}
    return {"drive": drive_root, "is_system": is_system, "admin": winapi.is_admin(), "growth": growth,
            "free": winapi.disk_free(drive_root), "items": results}


def clean(job, rule_ids, drive_root):
    rules = {r["id"]: r for r in RULES}
    admin = winapi.is_admin()
    free_before = winapi.disk_free(drive_root)
    report = []
    for n, rid in enumerate(rule_ids, 1):
        rule = rules.get(rid)
        if not rule or rule["group"] not in ("safe", "review") or rule.get("mode") == "info":
            continue  # never delete info/never rules, whatever the UI sends
        job.check()
        job.update(current=rule["name"]["es"], progress=(n - 1) / len(rule_ids))
        entry = {"id": rid, "name": rule["name"], "freed": 0, "deleted": 0, "skipped": 0, "note": None}
        report.append(entry)
        if rule.get("admin") and not admin:
            entry["note"] = T("Requiere administrador: se omitió.", "Needs administrator: skipped.")
            continue
        if rule.get("mode") == "recyclebin":
            size, count = winapi.recycle_bin_info(drive_root)
            if winapi.empty_recycle_bin(drive_root):
                entry.update(freed=size, deleted=count)
            continue
        stopped = []
        for svc in rule.get("services", []):
            rc, _ = winapi.run_hidden(["net", "stop", svc, "/y"], timeout=90)
            if rc == 0:
                stopped.append(svc)
        try:
            for path in _resolve(rule):
                if not _on_drive(path, drive_root):
                    continue
                if os.path.isfile(path):
                    try:
                        size = os.path.getsize(path)
                        if not rule.get("older") or os.path.getmtime(path) < time.time() - rule["older"] * fsutil.DAY:
                            os.remove(path)
                            entry["freed"] += size
                            entry["deleted"] += 1
                    except OSError:
                        entry["skipped"] += 1
                    continue
                freed, deleted, skipped = fsutil.delete_contents(path, rule.get("older", 0), job)
                entry["freed"] += freed
                entry["deleted"] += deleted
                entry["skipped"] += skipped
        finally:
            for svc in reversed(stopped):
                winapi.run_hidden(["net", "start", svc], timeout=90)
        if entry["skipped"]:
            entry["note"] = T("Algunos archivos estaban en uso y se dejaron.", "Some files were in use and were left alone.")
    job.update(progress=1)
    return {"drive": drive_root, "free_before": free_before, "free_after": winapi.disk_free(drive_root), "items": report}
