"""The object the web UI talks to (pywebview js_api, or the local HTTP bridge).

Public methods are callable from JavaScript; everything internal starts with
an underscore so pywebview does not expose it.
"""

import locale
import os
import sys

from . import APP_NAME, __version__, analyzer, cleanup, devprojects, duplicates, fsutil, history, organizer, scanner, winapi
from .jobs import JobManager


class Api:
    def __init__(self):
        self._jobs = JobManager()
        self._window = None

    # ------------------------------------------------------------ app
    def info(self):
        settings = fsutil.load_json("settings.json", {})
        lang = settings.get("lang")
        if lang not in ("es", "en"):
            loc = (locale.getlocale()[0] or "") + os.environ.get("LANG", "")
            lang = "es" if loc.lower().startswith(("es", "spanish")) else "en"
        return {
            "name": APP_NAME,
            "version": __version__,
            "admin": winapi.is_admin(),
            "windows": winapi.IS_WINDOWS,
            "lang": lang,
            "theme": settings.get("theme", "system"),
            "folders": winapi.user_folders(),
            "home": os.path.expanduser("~"),
            "native": self._window is not None,
            "python": sys.version.split()[0],
        }

    def save_settings(self, data):
        settings = fsutil.load_json("settings.json", {})
        settings.update({k: v for k, v in (data or {}).items() if k in ("lang", "theme")})
        fsutil.save_json("settings.json", settings)
        return settings

    def drives(self):
        drives = winapi.list_drives()
        try:
            history.log_free([d for d in drives if d["type"] == "fixed"])
        except OSError:
            pass
        return drives

    def relaunch_admin(self):
        if winapi.relaunch_as_admin():
            if self._window is not None:
                self._window.destroy()
            else:
                os._exit(0)
            return True
        return False

    def open_path(self, path):
        return winapi.open_in_explorer(path)

    def open_tool(self, name):
        return winapi.open_tool(name)

    def pick_folder(self, start=None):
        if self._window is None:
            return None  # browser mode: the UI asks for a typed path instead
        import webview
        dialog = getattr(getattr(webview, "FileDialog", None), "FOLDER", None)
        if dialog is None:
            dialog = webview.FOLDER_DIALOG
        res = self._window.create_file_dialog(dialog, directory=start or "")
        return res[0] if res else None

    def path_exists(self, path):
        return bool(path) and os.path.isdir(path)

    # ------------------------------------------------------------ jobs
    def job(self, job_id):
        return self._jobs.get(job_id)

    def cancel(self, job_id):
        return self._jobs.cancel(job_id)

    def _folder(self, path):
        if not path or not os.path.isdir(path):
            raise ValueError(f"La carpeta no existe / folder not found: {path}")
        return os.path.abspath(path)

    # ------------------------------------------------------------ features
    def cleanup_scan(self, drive_root):
        return self._jobs.start("cleanup-scan", cleanup.scan, drive_root)

    def cleanup_run(self, rule_ids, drive_root):
        return self._jobs.start("cleanup-run", cleanup.clean, list(rule_ids), drive_root)

    def disk_scan(self, root):
        return self._jobs.start("disk-scan", scanner.scan, self._folder(root))

    def disk_children(self, scan_id, rel=""):
        return scanner.children(scan_id, rel)

    def downloads_analyze(self, folder, lang="es"):
        return self._jobs.start("downloads", organizer.analyze_downloads, self._folder(folder), lang)

    def media_plan(self, folder, lang="es"):
        return self._jobs.start("media-plan", organizer.plan_media_by_date, self._folder(folder), lang)

    def plan_apply(self, plan_id, exclude=None):
        return self._jobs.start("plan-apply", organizer.apply_plan, plan_id, exclude or [])

    def undo_info(self, kind=None):
        return organizer.last_undo(kind)

    def undo_run(self, name):
        return self._jobs.start("undo", organizer.undo, name)

    def folder_analyze(self, folder):
        return self._jobs.start("analyze", analyzer.analyze, self._folder(folder))

    def duplicates_find(self, folders, min_mb=1):
        folders = [self._folder(f) for f in folders]
        return self._jobs.start("duplicates", duplicates.find, folders, int(float(min_mb) * 1024 * 1024))

    # ------------------------------------------------------------ history (v0.2)
    def history_roots(self):
        return history.roots()

    def history_compare(self, key, older_id=None, newer_id=None):
        return history.compare(key, older_id, newer_id)

    def history_free(self, drive):
        return history.free_series(drive)

    def history_used_change(self, drive, days=7):
        return history.used_change(drive, days)

    def history_rules(self, drive):
        growth = history.rule_growth(drive)
        names = {r["id"]: r["name"] for r in cleanup.RULES}
        for item in growth["items"]:
            item["name"] = names.get(item["id"], {"es": item["id"], "en": item["id"]})
        return growth

    # ------------------------------------------------------------ developer projects (v0.2)
    def dev_roots(self):
        return devprojects.default_roots(winapi.user_folders())

    def dev_scan(self, roots, inactive_days=90):
        roots = [self._folder(r) for r in roots]
        return self._jobs.start("dev-scan", devprojects.scan, roots, int(inactive_days))

    def delete(self, paths, permanent=False):
        def run(job, paths, permanent):
            job.update(message="deleting", progress=-1)
            results = fsutil.delete_paths(paths, permanent)
            return {"results": results,
                    "ok": sum(1 for r in results if r["ok"]),
                    "freed": sum(r["size"] for r in results if r["ok"]),
                    "permanent": permanent}
        return self._jobs.start("delete", run, list(paths), bool(permanent))
