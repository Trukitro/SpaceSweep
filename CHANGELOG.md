# Changelog

## 0.6.0 — 2026-11-11

- **Similar photos**: bursts, edited copies and resized versions. Thumbnails come from Windows itself (IShellItemImageFactory through ctypes), so any format Explorer can preview works without an image library. A 64-bit dHash plus banded grouping avoids comparing every pair, and clusters are re-checked so A~B~C chains don't merge unrelated photos. Results show thumbnails, and *keep the largest* selects the rest.
- **Installer** (`SpaceSweepSetup.exe`, Inno Setup): per-user, no admin, Spanish/English. Uninstalling removes the scheduled tasks too. The portable `SpaceSweep.exe` is still published.
- **README screenshots**, generated from the real window by `tools/screenshots.py` with demo data.
- Home lists every section with a one-line description.
- Downloads and My folders show the folder as `~\…` like the rest of the app.

## 0.5.0 — 2026-11-11

- **Duplicates against a backup**: point at your backup folder (for example on J:). Only files that already have an identical copy there are listed, and nothing in the backup is ever offered for deletion.
- **Move to another drive**: copies a heavy folder to another drive, verifies files and bytes, then swaps the original for a directory junction, so programs keep the same path and C: gets the space back. A failure at any step leaves the original untouched. There's a lock test for files in use and a list of moved folders with *Bring back*. It suggests typical candidates (LM Studio, Ollama, Hugging Face, Android SDK, Rust/Cargo, Gradle, Maven, NuGet) and adds a *move* button to every folder in Disk explorer.
- **WinSxS through DISM** (administrator): *Analyze* shows the real component-store size and whether cleanup is recommended; *Clean* runs `StartComponentCleanup`, keeping installed updates uninstallable.

## 0.4.0 — 2026-11-11

- **Programs**: every installed program with size, which is measured when Windows doesn't record it, plus install date and drive. Repeated versions are grouped (Windows SDK, Visual Studio Build Tools, Java, Python, SSMS…), and the page says which groups are normal and must stay (Visual C++ redistributables, .NET runtimes). Uninstall opens the program's own uninstaller, re-checked against the registry first.
- **Games**: Steam (all libraries), Epic, GOG, Ubisoft and Xbox games with size, drive and **last played** for Steam. Shows how much space games untouched for 90+ days take. Uninstall goes through the game's launcher.
- **Dev tools & AI**:
  - Docker reclaimable space with a prune button.
  - WSL/Docker virtual disks, with one click to enable WSL sparse mode.
  - Leftovers: old LM Studio `llama.cpp` engines (keeps the newest per variant and the selected one), obsolete VS Code extension folders, old JetBrains versions, Cargo/pnpm/Yarn/Gradle/Maven caches, Android virtual phones.
  - Every local AI model on its own: LM Studio, Hugging Face, and Ollama via `ollama rm`.

## 0.3.0 — 2026-11-11

- **Automatic upkeep** page, run by Windows Task Scheduler. Nothing stays resident and no administrator rights are needed:
  - *Low-space alert*: a daily check (plus 5 minutes after sign-in) shows a Windows notification when the system drive drops below the chosen free percentage, at most once a day.
  - *Weekly cleanup* of the "Safe to delete" Cleanup group, with a notification saying how much was freed.
  - *Downloads rules*: unfinished downloads and installers older than N days, plus exact copies, go to the Recycle Bin. Loose files can optionally be sorted by type.
  - Log of everything that ran automatically, a "test notification" button, and buttons to run the check or the cleanup now.
- New command-line modes: `--check` and `--clean-safe`, which do their job and exit.
- The sidebar is grouped into Free up space / Understand the drive / Organize / Keep it clean.

## 0.2.0 — 2026-11-11

- **History**: every disk scan and folder analysis keeps a compact snapshot. A new page compares two dates and lists what grew or shrank, down to the most specific folder. It also charts used space over time and shows which caches refill fastest.
- **Home** warns when the system drive's used space changed by 1 GB or more in the last week.
- **Code projects**: new page that finds regenerable folders (node_modules, venvs, Rust target, .NET bin/obj, JS/Gradle build caches). It shows each project's last activity, including git, pre-selects only inactive projects and shows the command that recreates each folder.
- Permanent deletes now handle paths longer than 260 characters (deep `node_modules`).
- Paths in the UI are shortened to `~\…` instead of showing your user folder.
- The .exe has its own icon, drawn at build time from the logo geometry (no image library).

## 0.1.0 — 2026-11-11

First release.

- Cleanup catalogue for the system drive with five risk groups (safe, your call, managed elsewhere, Windows settings, never touch), each item explained in Spanish and English.
- Disk explorer with parallel scan, drill-down, largest files, space by file type and unreadable/system space.
- Downloads: exact copies, unfinished downloads, old installers, extracted zips; sort by type with undo.
- My folders: analysis of Documents/Pictures/Videos/any folder, leftover detection (node_modules, venvs, Rust target, zipped backups, Office lock files, big logs), photos/videos by EXIF date with undo.
- Exact duplicate finder (size → edge hash → full BLAKE2), hard links ignored, at least one copy always kept.
- Native window (pywebview) or `--browser` mode on localhost with a per-run token.
- Standalone `SpaceSweep.exe` (~11 MB) built in an isolated environment; installable with pip so `python -m spacesweep` works from any folder.
