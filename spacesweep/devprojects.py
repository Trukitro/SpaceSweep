"""Developer projects: find regenerable folders (dependencies, virtual envs, build output)
inside code projects and say how long each project has been untouched.

A project is a folder with a marker file (package.json, pyproject.toml, Cargo.toml,
*.csproj, .git, ...). "Last activity" is the newest source file, ignoring the
regenerable folders themselves, plus git's index/HEAD when the project uses git.
"""

import os
import time

from .fsutil import dir_size, is_link_entry

DAY = 86400

MARKERS = {
    "package.json": "node", "pyproject.toml": "python", "requirements.txt": "python", "setup.py": "python",
    "pipfile": "python", "cargo.toml": "rust", "go.mod": "go", "pom.xml": "java", "build.gradle": "java",
    "build.gradle.kts": "java", "composer.json": "php", "gemfile": "ruby", "pubspec.yaml": "dart", ".git": "git",
}
MARKER_EXT = {".csproj": "dotnet", ".sln": "dotnet", ".fsproj": "dotnet", ".vbproj": "dotnet"}

# folder name -> (kind, how to get it back, is it "review" rather than plainly regenerable)
ALWAYS_JUNK = {
    "node_modules": ("node_modules", "npm install", False),
    "__pycache__": ("pycache", "", False),
    ".pytest_cache": ("pycache", "", False),
    ".mypy_cache": ("pycache", "", False),
    ".ruff_cache": ("pycache", "", False),
    ".tox": ("venv", "tox", False),
    ".next": ("build_cache", "npm run build", False),
    ".nuxt": ("build_cache", "npm run build", False),
    ".parcel-cache": ("build_cache", "npm run build", False),
    ".turbo": ("build_cache", "npm run build", False),
    ".svelte-kit": ("build_cache", "npm run build", False),
    ".angular": ("build_cache", "ng build", False),
    ".gradle": ("build_cache", "gradle build", False),
}
SKIP = {".git", "appdata", "$recycle.bin", "system volume information", "windows", "program files",
        "program files (x86)", "programdata", ".cache", ".lmstudio", ".ollama", ".rustup", ".cargo", ".nuget"}


def _junk_kind(name, entry_path, siblings):
    """Classify a sub-folder given the names (lower-case) present in its parent folder."""
    low = name.lower()
    if low in ALWAYS_JUNK:
        return ALWAYS_JUNK[low]
    if low in ("venv", ".venv", "env", ".env") and os.path.isfile(os.path.join(entry_path, "pyvenv.cfg")):
        return ("venv", "python -m venv .venv && pip install -r requirements.txt", False)
    if low == "target" and "cargo.toml" in siblings:
        return ("build_cache", "cargo build", False)
    if low in ("bin", "obj") and any(s.endswith((".csproj", ".fsproj", ".vbproj")) for s in siblings):
        return ("build_cache", "dotnet build", False)
    if low == "build" and ("build.gradle" in siblings or "build.gradle.kts" in siblings):
        return ("build_cache", "gradle build", False)
    if low in ("build", "dist") and ({"pyproject.toml", "setup.py"} & siblings):
        return ("dist", "python -m build / pyinstaller", True)  # may hold a release you want to keep
    return None


def default_roots(folders):
    home = os.path.expanduser("~")
    cands = [folders.get("documents"), folders.get("desktop")] + [
        os.path.join(home, n) for n in ("source", "repos", "projects", "Projects", "dev", "code", "src", "git", "GitHub")]
    seen, out = set(), []
    for c in cands:
        if c and os.path.isdir(c) and os.path.normcase(c) not in seen:
            seen.add(os.path.normcase(c))
            out.append(c)
    return out


def scan(job, roots, inactive_days=90, min_size=1024 * 1024):
    now = time.time()
    projects = {}  # path -> record
    order = []

    def project(path, kinds):
        rec = projects.get(path)
        if rec is None:
            rec = {"path": path, "name": os.path.basename(path) or path, "kinds": sorted(kinds), "last": 0.0, "junk": []}
            projects[path] = rec
            order.append(rec)
        return rec

    seen_roots, used_roots = set(), []
    count = 0
    for root in roots:
        root = os.path.abspath(root)
        if os.path.normcase(root) in seen_roots or not os.path.isdir(root):
            continue
        seen_roots.add(os.path.normcase(root))
        used_roots.append(root)
        stack = [(root, None)]
        while stack:
            current, owner = stack.pop()
            try:
                with os.scandir(current) as it:
                    entries = list(it)
            except OSError:
                continue
            names = {e.name.lower() for e in entries}
            kinds = {MARKERS[n] for n in names if n in MARKERS}
            kinds |= {MARKER_EXT[os.path.splitext(n)[1]] for n in names if os.path.splitext(n)[1] in MARKER_EXT}
            if kinds:
                owner = project(current, kinds)
                if ".git" in names:
                    for g in ("index", "HEAD", os.path.join("logs", "HEAD")):
                        try:
                            owner["last"] = max(owner["last"], os.stat(os.path.join(current, ".git", g)).st_mtime)
                        except OSError:
                            pass
            for e in entries:
                try:
                    if e.is_dir(follow_symlinks=False):
                        if is_link_entry(e) or e.name.lower() in SKIP:
                            continue
                        jk = _junk_kind(e.name, e.path, names)
                        if jk:
                            size, files = dir_size(e.path, job=job)
                            if size:
                                target = owner or project(current, {"other"})
                                target["junk"].append({"path": e.path, "kind": jk[0], "regen": jk[1], "review": jk[2],
                                                       "size": size, "files": files})
                            continue
                        stack.append((e.path, owner))
                    elif owner is not None:
                        owner["last"] = max(owner["last"], e.stat(follow_symlinks=False).st_mtime)
                except OSError:
                    continue
            count += 1
            if count % 200 == 0:
                job.check()
                job.update(current=current, count=len(order))

    result = []
    for rec in order:
        rec["junk_size"] = sum(j["size"] for j in rec["junk"])
        if rec["junk_size"] < min_size:
            continue  # a few KB of __pycache__ is not worth a row
        rec["junk"].sort(key=lambda j: -j["size"])
        rec["idle_days"] = int((now - rec["last"]) // DAY) if rec["last"] else None
        rec["inactive"] = rec["idle_days"] is None or rec["idle_days"] >= inactive_days
        result.append(rec)
    result.sort(key=lambda r: -r["junk_size"])
    return {"roots": used_roots, "projects": result, "inactive_days": inactive_days,
            "total": sum(r["junk_size"] for r in result),
            "inactive_total": sum(j["size"] for r in result if r["inactive"] for j in r["junk"] if not j["review"])}
