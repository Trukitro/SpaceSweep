# Changelog

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
