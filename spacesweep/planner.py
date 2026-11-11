"""'Free N GB' assistant: one plan that combines every SpaceSweep source, safest first.

The plan only *points* at the right page; each step is still carried out (and
confirmed) on its own page, with its own explanation. Risk levels:
  0 nothing is lost (caches)          1 something small is lost (Recycle Bin, rebuildable deps)
  2 data stays but changes place/form (compress, move)    3 something must be reinstalled (games)
"""

import os
import shutil

from . import cleanup, devprojects, inventory, mover, winapi
from .compress import candidates as compress_candidates

GAME_IDLE_DAYS = 180
COMPRESS_GUESS = 0.25  # typical LZX saving on installed games/tools; shown as an estimate


def T(es, en):
    return {"es": es, "en": en}


def _on(path, drive_root):
    return os.path.splitdrive(os.path.abspath(path))[0].upper() == os.path.splitdrive(drive_root)[0].upper()


def build(job, drive_root, target_bytes):
    steps = []
    admin = winapi.is_admin()

    job.update(message="cleanup", progress=0.05)
    scan = cleanup.scan(job, drive_root)
    safe = [i for i in scan["items"] if i["group"] == "safe" and i["exists"] and i["measured"] and i["size"] > 0]
    free_now = [i for i in safe if admin or not i["admin"]]
    need_admin = [i for i in safe if i["admin"] and not admin]
    if free_now:
        steps.append({"id": "cleanup_safe", "risk": 0, "page": "cleanup", "size": sum(i["size"] for i in free_now),
                      "title": T("Limpieza: grupo «Seguro de borrar»", "Cleanup: \"Safe to delete\" group"),
                      "detail": T(f"{len(free_now)} cachés y temporales que se regeneran solos.",
                                  f"{len(free_now)} caches and temp files that rebuild themselves.")})
    if need_admin:
        steps.append({"id": "cleanup_admin", "risk": 0, "page": "cleanup", "size": sum(i["size"] for i in need_admin),
                      "title": T("Limpieza que requiere administrador", "Cleanup that needs administrator"),
                      "detail": T("Windows Update, Temp del sistema… Reinicia SpaceSweep como administrador.",
                                  "Windows Update, system Temp… Restart SpaceSweep as administrator.")})
    review = {i["id"]: i for i in scan["items"] if i["group"] == "review" and i["measured"] and i["size"] > 0}
    if "recycle_bin" in review:
        steps.append({"id": "recycle_bin", "risk": 1, "page": "cleanup", "size": review["recycle_bin"]["size"],
                      "title": T("Vaciar la Papelera", "Empty the Recycle Bin"),
                      "detail": T("Archivos que ya borraste; no se pueden recuperar después.", "Files you already deleted; no undo after this.")})
    other_review = [i for k, i in review.items() if k != "recycle_bin"]
    if other_review:
        steps.append({"id": "cleanup_review", "risk": 1, "page": "cleanup", "size": sum(i["size"] for i in other_review),
                      "title": T("Limpieza: «Decisión tuya»", "Cleanup: \"Your call\""),
                      "detail": T("Shaders de juegos, imágenes de emulador, caché de Spotify…", "Game shaders, emulator images, Spotify cache…")})

    job.update(message="projects", progress=0.25)
    roots = [r for r in devprojects.default_roots(winapi.user_folders()) if _on(r, drive_root)]
    if roots:
        dev = devprojects.scan(job, roots)
        size = sum(j["size"] for p in dev["projects"] if p["inactive"] for j in p["junk"] if not j["review"])
        if size:
            steps.append({"id": "projects", "risk": 1, "page": "projects", "size": size,
                          "title": T("Proyectos de programación inactivos", "Inactive code projects"),
                          "detail": T("node_modules, entornos virtuales y compilaciones; se recrean con un comando.",
                                      "node_modules, virtual envs and builds; one command recreates them.")})

    job.update(message="devtools", progress=0.5)
    left = [x for x in inventory.lmstudio_runtimes() + inventory.vscode_leftovers() + inventory.jetbrains_leftovers()
            if _on(x["path"], drive_root)]
    if left:
        steps.append({"id": "devtools", "risk": 1, "page": "devtools", "size": sum(x["size"] for x in left),
                      "title": T("Sobras de herramientas de desarrollo", "Developer tool leftovers"),
                      "detail": T("Motores viejos de LM Studio, extensiones obsoletas, versiones viejas de JetBrains.",
                                  "Old LM Studio engines, obsolete extensions, old JetBrains versions.")})

    job.update(message="compress", progress=0.6)
    comp = [c for c in compress_candidates(job) if _on(c["path"], drive_root)]
    if comp:
        steps.append({"id": "compress", "risk": 2, "page": "compress", "size": int(sum(c["size"] for c in comp) * COMPRESS_GUESS),
                      "estimate": True,
                      "title": T("Comprimir juegos y herramientas (sin borrar)", "Compress games and tools (nothing deleted)"),
                      "detail": T(f"{len(comp)} carpetas. Estimado aproximado; la página Comprimir calcula el valor real.",
                                  f"{len(comp)} folders. Rough estimate; the Compress page measures the real value.")})

    job.update(message="move", progress=0.8)
    others = [d for d in winapi.list_drives() if d["type"] == "fixed" and not _on(d["root"], drive_root)]
    if others:
        sugg = [s for s in mover.suggestions() if _on(s["path"], drive_root)]
        room = max(d["free"] for d in others)
        size = min(room // 2, sum(s["size"] for s in sugg))
        if size:
            steps.append({"id": "move", "risk": 2, "page": "move", "size": size,
                          "title": T("Mover carpetas pesadas a otro disco", "Move heavy folders to another drive"),
                          "detail": T("Modelos de IA, SDKs, cachés de compilación; siguen funcionando por enlace.",
                                      "AI models, SDKs, build caches; they keep working through a link.")})

    job.update(message="games", progress=0.9)
    idle = [g for g in inventory.games(job)["games"] if _on(g["path"], drive_root)
            and g["idle_days"] is not None and g["idle_days"] >= GAME_IDLE_DAYS]
    if idle:
        steps.append({"id": "games", "risk": 3, "page": "games", "size": sum(g["size"] for g in idle),
                      "title": T(f"Desinstalar juegos sin jugar en {GAME_IDLE_DAYS}+ días", f"Uninstall games unplayed for {GAME_IDLE_DAYS}+ days"),
                      "detail": T(f"{len(idle)} juegos; se vuelven a descargar desde su tienda si los quieres.",
                                  f"{len(idle)} games; download again from their store if you want them back.")})

    steps.sort(key=lambda s: (s["risk"], -s["size"]))
    total = 0
    for s in steps:
        total += s["size"]
        s["cumulative"] = total
        s["reaches"] = total >= target_bytes
    usage = shutil.disk_usage(drive_root)
    return {"drive": drive_root, "target": target_bytes, "free": usage.free, "total_possible": total,
            "reachable": total >= target_bytes, "steps": steps}
