"""Automatic upkeep without a resident process.

Windows Task Scheduler starts SpaceSweep briefly with `--check` (daily) or
`--clean-safe` (weekly); each run does its job in a second or two and exits.
Nothing stays in memory, nothing needs administrator rights.

  --check       log free space, warn with a Windows notification when the
                system drive is low, apply the Downloads rules if enabled
  --clean-safe  clean the "safe" Cleanup group and report what was freed
"""

import base64
import os
import subprocess
import sys
import tempfile
import time
from xml.sax.saxutils import escape

from . import APP_NAME, cleanup, fsutil, history, organizer, winapi
from .jobs import Job

TASK_FOLDER = APP_NAME
TASKS = {"check": "Daily check", "clean": "Weekly clean"}
DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
DAY_XML = {"MON": "Monday", "TUE": "Tuesday", "WED": "Wednesday", "THU": "Thursday", "FRI": "Friday",
           "SAT": "Saturday", "SUN": "Sunday"}

DEFAULTS = {
    "alert": {"enabled": False, "percent": 10, "time": "10:00"},
    "weekly_clean": {"enabled": False, "day": "SUN", "time": "12:00"},
    "downloads": {"enabled": False, "partial_days": 7, "installer_days": 30, "duplicates": True, "organize": False},
}

TEXT = {
    "low_t": {"es": "Queda poco espacio en {d}", "en": "Low disk space on {d}"},
    "low_b": {"es": "Solo {free} libres ({pct}%). Abre SpaceSweep → Limpieza para liberar espacio.",
              "en": "Only {free} free ({pct}%). Open SpaceSweep → Cleanup to free space."},
    "clean_t": {"es": "SpaceSweep liberó {freed}", "en": "SpaceSweep freed {freed}"},
    "clean_b": {"es": "Limpieza semanal de cachés y temporales en {d}.", "en": "Weekly cleanup of caches and temp files on {d}."},
    "dl_t": {"es": "Descargas ordenada", "en": "Downloads tidied"},
    "dl_b": {"es": "{n} archivos a la Papelera ({size}), {m} archivos ordenados.",
             "en": "{n} files to the Recycle Bin ({size}), {m} files sorted."},
}


def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024


# ---------------------------------------------------------------- settings

def get_settings():
    saved = fsutil.load_json("settings.json", {}).get("auto", {})
    out = {}
    for k, v in DEFAULTS.items():
        out[k] = dict(v, **{kk: vv for kk, vv in saved.get(k, {}).items() if kk in v})
    return out


def _validate(s):
    a, w, d = s["alert"], s["weekly_clean"], s["downloads"]
    a["percent"] = max(1, min(50, int(a["percent"])))
    for block in (a, w):
        hh, mm = str(block["time"]).split(":")[:2]
        block["time"] = f"{max(0, min(23, int(hh))):02d}:{max(0, min(59, int(mm))):02d}"
    if w["day"] not in DAYS:
        w["day"] = "SUN"
    d["partial_days"] = max(1, int(d["partial_days"]))
    d["installer_days"] = max(1, int(d["installer_days"]))
    for block in (a, w, d):
        block["enabled"] = bool(block["enabled"])
    d["duplicates"], d["organize"] = bool(d["duplicates"]), bool(d["organize"])
    return s


def save_settings(new, lang="es", register=True):
    s = get_settings()
    for k in DEFAULTS:
        if k in (new or {}):
            s[k].update({kk: vv for kk, vv in new[k].items() if kk in DEFAULTS[k]})
    s = _validate(s)
    all_settings = fsutil.load_json("settings.json", {})
    all_settings["auto"] = s
    fsutil.save_json("settings.json", all_settings)
    result = {"settings": s, "tasks": {}}
    if register:
        result["tasks"] = sync_tasks(s)
    return result


# ---------------------------------------------------------------- task scheduler

def launcher_command(mode):
    """(program, arguments) that start SpaceSweep in `mode` without any window."""
    if getattr(sys, "frozen", False):
        return sys.executable, f"--{mode}"
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pyw):
        pyw = sys.executable
    # A tiny launcher that imports SpaceSweep from wherever it is running now.
    pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(fsutil.app_data_dir(), "task_launcher.pyw")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write("import os, sys\n"
                 f"p = {pkg_parent!r}\n"
                 "if os.path.isdir(os.path.join(p, 'spacesweep')) and p not in sys.path:\n"
                 "    sys.path.insert(0, p)\n"
                 "from spacesweep.__main__ import main\n"
                 "main()\n")
    return pyw, f'"{script}" --{mode}'


def current_user():
    user = os.environ.get("USERNAME", "")
    domain = os.environ.get("USERDOMAIN", "")
    return f"{domain}\\{user}" if domain else user


def task_xml(mode, s):
    prog, args = launcher_command(mode)
    user = escape(current_user())
    if mode == "check":
        hhmm = s["alert"]["time"]
        # The logon trigger must name the user: "any user" logon triggers need administrator rights.
        trigger = f"<CalendarTrigger><StartBoundary>2026-01-01T{hhmm}:00</StartBoundary><Enabled>true</Enabled>" \
                  f"<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>" \
                  f"<LogonTrigger><Enabled>true</Enabled><UserId>{user}</UserId><Delay>PT5M</Delay></LogonTrigger>"
    else:
        hhmm = s["weekly_clean"]["time"]
        trigger = f"<CalendarTrigger><StartBoundary>2026-01-01T{hhmm}:00</StartBoundary><Enabled>true</Enabled>" \
                  f"<ScheduleByWeek><DaysOfWeek><{DAY_XML[s['weekly_clean']['day']]} /></DaysOfWeek>" \
                  f"<WeeksInterval>1</WeeksInterval></ScheduleByWeek></CalendarTrigger>"
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>{escape(APP_NAME)}: {escape(mode)}</Description></RegistrationInfo>
  <Triggers>{trigger}</Triggers>
  <Principals><Principal id="Author"><UserId>{user}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author"><Exec><Command>{escape(prog)}</Command><Arguments>{escape(args)}</Arguments></Exec></Actions>
</Task>"""


def task_name(mode):
    # Root of the library: creating a sub-folder in Task Scheduler needs administrator rights.
    return f"\\{TASK_FOLDER} - {TASKS[mode]}"


def register_task(mode, s, name=None):
    name = name or task_name(mode)
    fd, path = tempfile.mkstemp(suffix=".xml")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-16") as fh:
            fh.write(task_xml(mode, s))
        rc, out = winapi.run_hidden(["schtasks", "/Create", "/F", "/TN", name, "/XML", path], timeout=30)
    finally:
        os.remove(path)
    return rc == 0, out.strip()


def delete_task(name):
    rc, out = winapi.run_hidden(["schtasks", "/Delete", "/F", "/TN", name], timeout=30)
    return rc == 0, out.strip()


def task_info(name):
    rc, out = winapi.run_hidden(["schtasks", "/Query", "/TN", name, "/FO", "CSV", "/NH"], timeout=30)
    if rc != 0:
        return None
    cols = [c.strip('"') for c in out.strip().splitlines()[-1].split('","')]
    return {"name": name, "next_run": cols[1] if len(cols) > 1 else "", "status": cols[2] if len(cols) > 2 else ""}


def sync_tasks(s):
    """Make the scheduled tasks match the settings. Returns {mode: {ok, message}}."""
    out = {}
    wanted = {"check": s["alert"]["enabled"] or s["downloads"]["enabled"], "clean": s["weekly_clean"]["enabled"]}
    for mode, on in wanted.items():
        if on:
            ok, msg = register_task(mode, s)
        else:
            ok, msg = (delete_task(task_name(mode)) if task_info(task_name(mode)) else (True, ""))
        out[mode] = {"ok": ok, "enabled": on, "message": msg}
    return out


def status():
    s = get_settings()
    return {"settings": s, "tasks": {m: task_info(task_name(m)) for m in TASKS}, "log": read_log()[-30:][::-1],
            "launcher": launcher_command("check")[0]}


# ---------------------------------------------------------------- notifications

def notify(title, body):
    """Windows toast through PowerShell's registered app id (works on Windows 10/11 with no extra package)."""
    if not winapi.IS_WINDOWS:
        return False
    xml = (f"<toast><visual><binding template='ToastGeneric'><text>{escape(title)}</text>"
           f"<text>{escape(body)}</text></binding></visual></toast>")
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null;"
        "$x = New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f"$x.LoadXml(@'\n{xml}\n'@);"
        "$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe';"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show("
        "[Windows.UI.Notifications.ToastNotification]::new($x))"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    rc, _ = winapi.run_hidden(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                               "-EncodedCommand", encoded], timeout=30)
    return rc == 0


# ---------------------------------------------------------------- activity log

def log_action(kind, details):
    data = fsutil.load_json(os.path.join("history", "auto.json"), [])
    data.append({"time": time.time(), "kind": kind, **details})
    fsutil.save_json(os.path.join("history", "auto.json"), data[-200:])


def read_log():
    return fsutil.load_json(os.path.join("history", "auto.json"), [])


def _lang():
    lang = fsutil.load_json("settings.json", {}).get("lang")
    return lang if lang in ("es", "en") else "es"


def _t(key, **kw):
    return TEXT[key].get(_lang(), TEXT[key]["es"]).format(**kw)


# ---------------------------------------------------------------- the jobs themselves

def system_drive():
    return os.environ.get("SystemDrive", "C:") + "\\"


def run_check(now=None, usage=None, notifier=notify):
    s = get_settings()
    now = now or time.time()
    report = {"alert": None, "downloads": None}
    try:
        history.log_free(min_gap=3600)
    except OSError:
        pass
    drive = system_drive()
    if s["alert"]["enabled"]:
        import shutil
        u = usage or shutil.disk_usage(drive)
        pct = u.free * 100 / u.total if u.total else 100
        last = fsutil.load_json("settings.json", {}).get("auto_last_alert", 0)
        if pct < s["alert"]["percent"] and now - last > 20 * 3600:
            notifier(_t("low_t", d=drive[:2]), _t("low_b", free=human(u.free), pct=f"{pct:.0f}"))
            all_s = fsutil.load_json("settings.json", {})
            all_s["auto_last_alert"] = now
            fsutil.save_json("settings.json", all_s)
            log_action("alert", {"drive": drive, "free": u.free, "percent": round(pct, 1)})
            report["alert"] = round(pct, 1)
    if s["downloads"]["enabled"]:
        report["downloads"] = run_downloads_rules(s["downloads"], notifier=notifier)
    return report


def pick_download_deletions(analysis, rules):
    out = []
    for f in analysis["suggestions"]:
        if f["reason"] == "partial" and f["age"] >= rules["partial_days"]:
            out.append(f)
        elif f["reason"] == "old_installer" and f["age"] >= rules["installer_days"]:
            out.append(f)
        elif f["reason"] == "duplicate" and rules["duplicates"]:
            out.append(f)
    return out


def run_downloads_rules(rules, folder=None, notifier=notify):
    folder = folder or winapi.known_folder("downloads")
    if not os.path.isdir(folder):
        return None
    job = Job("auto-downloads")
    analysis = organizer.analyze_downloads(job, folder, _lang(), installer_days=rules["installer_days"])
    victims = pick_download_deletions(analysis, rules)
    deleted = fsutil.delete_paths([v["path"] for v in victims], permanent=False) if victims else []
    ok = [r for r in deleted if r["ok"]]
    moved = 0
    if rules["organize"]:
        fresh = organizer.analyze_downloads(job, folder, _lang())
        moved = organizer.apply_plan(job, fresh["plan_id"])["moved"]
    result = {"recycled": len(ok), "bytes": sum(r["size"] for r in ok), "sorted": moved,
              "files": [os.path.basename(r["path"]) for r in ok][:50]}
    if ok or moved:
        log_action("downloads", result)
        notifier(_t("dl_t"), _t("dl_b", n=len(ok), size=human(result["bytes"]), m=moved))
    return result


def run_clean_safe(notifier=notify):
    drive = system_drive()
    job = Job("auto-clean")
    scan = cleanup.scan(job, drive)
    admin = winapi.is_admin()
    ids = [i["id"] for i in scan["items"] if i["group"] == "safe" and i["size"] > 0 and i["exists"]
           and (admin or not i["admin"])]
    report = cleanup.clean(job, ids, drive) if ids else {"items": [], "free_before": 0, "free_after": 0}
    freed = sum(i["freed"] for i in report["items"])
    log_action("clean", {"drive": drive, "freed": freed, "items": [i["id"] for i in report["items"] if i["freed"]]})
    if freed >= 50 * 1024 * 1024:
        notifier(_t("clean_t", freed=human(freed)), _t("clean_b", d=drive[:2]))
    return {"freed": freed, "items": report["items"]}
