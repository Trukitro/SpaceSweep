# Changelog

## 0.1.0 — 2026-11-11

First release.

- Cleanup catalogue for the system drive with five risk groups (safe, your call, managed elsewhere, Windows settings, never touch), each item explained in Spanish and English.
- Disk explorer with parallel scan, drill-down, largest files, space by file type and unreadable/system space.
- Downloads: exact copies, unfinished downloads, old installers, extracted zips; sort by type with undo.
- My folders: analysis of Documents/Pictures/Videos/any folder, leftover detection (node_modules, venvs, Rust target, zipped backups, Office lock files, big logs), photos/videos by EXIF date with undo.
- Exact duplicate finder (size → edge hash → full BLAKE2), hard links ignored, at least one copy always kept.
- Native window (pywebview) or `--browser` mode on localhost with a per-run token.
