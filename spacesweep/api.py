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
        self._startup_path = None

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
            "check_updates": settings.get("check_updates", True),
            "folders": winapi.user_folders(),
            "home": os.path.expanduser("~"),
            "native": self._window is not None,
            "python": sys.version.split()[0],
        }

    def save_settings(self, data):
        settings = fsutil.load_json("settings.json", {})
        settings.update({k: v for k, v in (data or {}).items() if k in ("lang", "theme", "check_updates")})
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

    def duplicates_find(self, folders, min_mb=1, reference=None):
        folders = [self._folder(f) for f in folders]
        reference = [self._folder(f) for f in (reference or [])]
        return self._jobs.start("duplicates", duplicates.find, folders, int(float(min_mb) * 1024 * 1024), reference)

    # ------------------------------------------------------------ move to another drive (v0.5)
    def move_check(self, src, dest_root):
        from . import mover
        size, files, target = mover.check(src, dest_root)
        return {"size": size, "files": files, "target": target}

    def move_run(self, src, dest_root):
        from . import mover
        return self._jobs.start("move", mover.move, src, dest_root)

    def move_restore(self, src):
        from . import mover
        return self._jobs.start("move-restore", mover.restore, src)

    def move_list(self):
        from . import mover
        return mover.list_moves()

    def move_suggestions(self):
        from . import mover
        return self._jobs.start("move-suggest", lambda job: mover.suggestions())

    # ------------------------------------------------------------ similar photos (v0.6)
    def photos_find(self, folders, threshold=6):
        from . import photos
        folders = [self._folder(f) for f in folders]
        return self._jobs.start("photos", photos.find_similar, folders, max(1, min(15, int(threshold))))

    def photo_thumb(self, path, px=120):
        from . import photos
        if not os.path.isfile(path):
            return None
        return photos.thumb_data_uri(path, int(px))

    # ------------------------------------------------------------ compress / planner / updates (v0.7)
    def compress_candidates(self):
        from . import compress
        return self._jobs.start("compress-candidates", lambda job: compress.candidates(job))

    def compress_status(self, path):
        from . import compress
        return self._jobs.start("compress-status", compress.status, self._folder(path))

    def compress_run(self, path, algo="LZX"):
        from . import compress
        return self._jobs.start("compress", compress.compress, self._folder(path), algo)

    def compress_undo(self, path):
        from . import compress
        return self._jobs.start("decompress", compress.decompress, self._folder(path))

    def plan_build(self, drive_root, target_gb):
        from . import planner
        return self._jobs.start("plan", planner.build, drive_root, int(float(target_gb) * 1024 ** 3))

    def update_check(self, force=False):
        from . import updates
        return updates.check(bool(force))

    def changelog(self):
        from . import updates
        return updates.changelog()

    def whats_new(self):
        from . import updates
        return updates.whats_new()

    def open_url(self, url):
        import webbrowser
        if not str(url).startswith("https://github.com/Trukitro/SpaceSweep"):
            raise ValueError("only SpaceSweep release links are opened")
        return webbrowser.open(url)

    # ------------------------------------------------------------ report (v1.0)
    def report_export(self, lang="es"):
        from . import report
        return self._jobs.start("report", report.export, None, lang if lang in ("es", "en") else "es")

    def report_open(self, path):
        name = os.path.basename(str(path))
        if not (name.startswith("SpaceSweep-report-") and name.endswith((".html", ".csv")) and os.path.isfile(path)):
            raise ValueError("not a SpaceSweep report")
        os.startfile(path)
        return True

    # ------------------------------------------------------------ hard links / shell menu / restore points (v0.9)
    def startup_path(self):
        path, self._startup_path = self._startup_path, None
        return path

    def duplicates_hardlink(self, pairs):
        pairs = [(str(d), str(k)) for d, k in pairs]
        return self._jobs.start("hardlink", duplicates.hardlink, pairs)

    def shellmenu_status(self):
        from . import shellmenu
        return shellmenu.status()

    def shellmenu_set(self, on, lang="es"):
        from . import shellmenu
        return shellmenu.install(lang) if on else shellmenu.uninstall()

    def restore_points(self):
        from . import winmaint
        return self._jobs.start("restore-points", lambda job: winmaint.restore_points())

    def restore_delete_oldest(self, drive="C:"):
        from . import winmaint
        return self._jobs.start("restore-delete", lambda job: winmaint.delete_oldest_restore_point(drive))

    # ------------------------------------------------------------ recycle bin / recordings (v0.8)
    def recycle_summary(self):
        from . import recyclebin
        return self._jobs.start("recycle", lambda job: recyclebin.summary())

    def recycle_empty_older(self, days):
        from . import recyclebin
        days = int(days)
        if days < 1:
            raise ValueError("days must be >= 1")
        return self._jobs.start("recycle-empty", lambda job: recyclebin.empty_older_than(days, job=job))

    def recordings_scan(self):
        from . import recordings
        return self._jobs.start("recordings", recordings.scan)

    # ------------------------------------------------------------ component store (v0.5)
    def dism_analyze(self):
        from . import winmaint
        return self._jobs.start("dism-analyze", winmaint.analyze)

    def dism_cleanup(self):
        from . import winmaint
        return self._jobs.start("dism-clean", winmaint.cleanup)

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

    # ------------------------------------------------------------ automation (v0.3)
    def auto_status(self):
        from . import automation
        return automation.status()

    def auto_save(self, settings):
        from . import automation
        return automation.save_settings(settings)

    def auto_test_notify(self, title, body):
        from . import automation
        return automation.notify(title, body)

    def auto_run(self, mode):
        from . import automation

        def run(job, mode):
            job.update(progress=-1)
            return automation.run_check() if mode == "check" else automation.run_clean_safe()
        return self._jobs.start("auto-run", run, mode)

    # ------------------------------------------------------------ inventory (v0.4)
    def inv_programs(self):
        from . import inventory
        return self._jobs.start("programs", lambda job: inventory.programs(job))

    def inv_uninstall(self, program_id, command):
        from . import inventory
        return inventory.uninstall_program(program_id, command)

    def inv_games(self):
        from . import inventory
        return self._jobs.start("games", lambda job: inventory.games(job))

    def inv_game_uninstall(self, platform, game_id):
        from . import inventory
        return inventory.game_uninstall(platform, str(game_id))

    def inv_devtools(self):
        from . import inventory

        def run(job):
            data = inventory.devtools(job)
            data["models"] = inventory.ai_models()
            return data
        return self._jobs.start("devtools", run)

    def inv_docker_prune(self, all_images=False):
        from . import inventory
        return self._jobs.start("docker-prune", lambda job: inventory.docker_prune(bool(all_images)))

    def inv_wsl_sparse(self, name):
        from . import inventory
        names = {d["name"] for d in inventory.wsl_distros() if not d.get("docker")}
        if name not in names:
            raise ValueError("unknown distro")
        return self._jobs.start("wsl-sparse", lambda job: inventory.wsl_set_sparse(name))

    def inv_ollama_rm(self, name):
        from . import inventory
        return inventory.ollama_rm(name)

    def delete(self, paths, permanent=False):
        def run(job, paths, permanent):
            job.update(message="deleting", progress=-1)
            results = fsutil.delete_paths(paths, permanent)
            return {"results": results,
                    "ok": sum(1 for r in results if r["ok"]),
                    "freed": sum(r["size"] for r in results if r["ok"]),
                    "permanent": permanent}
        return self._jobs.start("delete", run, list(paths), bool(permanent))
