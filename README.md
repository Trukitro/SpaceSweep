<p align="center">
  <img src="spacesweep/ui/logo.svg" alt="SpaceSweep logo" width="120">
</p>

<h1 align="center">SpaceSweep</h1>

<p align="center">Free up disk space on Windows without guessing what is safe to delete.</p>

SpaceSweep finds caches, leftovers, duplicates and forgotten big files, and tells you in plain language **what each thing is, what happens if you delete it, and what you should never touch**. It focuses on the Windows system drive (C:) but works on any drive or folder. The interface is available in Spanish and English.

It is a small native window (pywebview + HTML/CSS/JS) on top of a pure-Python engine: **one dependency, no admin rights needed for most features, nothing deleted without a confirmation that lists exactly what goes.**

---

## Features

- **Cleanup**: measures 20+ known space hogs and sorts them into:
  - *Safe to delete*: temp files, NVIDIA/AMD/DirectX shader caches, used driver installers, Windows Update downloads, crash dumps, thumbnail and browser caches, dev caches (pip, npm, yarn, uv, NuGet, Go).
  - *Your call*: Recycle Bin, game shader caches, Android emulator images, Spotify cache, Unity installers.
  - *Big, managed elsewhere*: WSL/Docker disks and local AI models (LM Studio, Ollama, Hugging Face), with how to shrink them.
  - *You change these in Windows*: page file, hibernation file, restore points, with a button to the right settings page.
  - *Never touch*: `Windows\Installer`, `WinSxS`, `DriverStore`, and why.
- **Disk explorer**: scans a whole drive or folder (parallel `os.scandir`), then lets you drill into folders instantly. It also shows the largest files, space per file type, and how much used space could not be read (restore points, system files).
- **Downloads**: finds exact copies (`setup (1).exe`), unfinished downloads, old installers and zips you already extracted. Sorts loose files into folders by type, **with undo**.
- **My folders**: analyzes Documents, Pictures, Videos, Music, Desktop or any folder: space per file type, biggest subfolders, biggest files, big files untouched for 2+ years. It flags likely leftovers: `node_modules`, Python virtual environments, Rust `target` folders, `.bak` backups you already zipped, Office lock files, big logs. It can also sort loose photos and videos into `Year\Year-Month` folders using the camera's EXIF date, **with undo**.
- **Duplicates**: byte-for-byte identical files across any set of folders. Files are compared by size, then the first and last 64 KB, then a full BLAKE2 hash. Hard links are ignored, and at least one copy of each group is always kept.
- **Safe by default**: your own files go to the Recycle Bin unless you tick *delete permanently*. Caches are deleted for good because they rebuild themselves. Files in use are skipped, never forced, and SpaceSweep refuses to delete drive roots, Windows folders or your profile folders.
- **Light / dark / system theme** and **Spanish / English**, both remembered.

---

## Installation

### Download (recommended)

1. Go to [Releases](https://github.com/Trukitro/SpaceSweep/releases) and download `SpaceSweep.exe` (about 11 MB, nothing to install).
2. Double-click it. If Windows SmartScreen warns you (the .exe isn't code-signed), click **More info** → **Run anyway**.

It needs the Microsoft Edge WebView2 runtime, which is already part of Windows 11 and of updated Windows 10.

### Run from source

**Requirements**: Windows 10/11, Python 3.10+, and the Microsoft Edge WebView2 runtime (already included in Windows 11).

```bash
git clone https://github.com/Trukitro/SpaceSweep.git
python -m pip install -e SpaceSweep
```

That installs the `spacesweep` command, so from then on it starts from **any** terminal and any folder:

```bash
spacesweep
```

`python -m spacesweep` works too. Double-clicking `SpaceSweep.pyw` starts it without a console window.

### Build a standalone app

```powershell
.\build.ps1            # folder build in dist\SpaceSweep\ (fastest start-up)
.\build.ps1 -OneFile   # single dist\SpaceSweep.exe
```

The script builds inside an isolated `.build-venv`, so only `pywebview` ends up in the .exe and your global Python is never modified.

---

## Usage

```bash
spacesweep              # native window
spacesweep --browser    # same UI in your web browser (also the automatic fallback without WebView2)
spacesweep --debug      # native window with developer tools
```

Most features work as a normal user. Cleaning **Windows Update downloads**, the **system Temp folder** and **Delivery Optimization** needs administrator rights. Use *Restart as admin* in the sidebar to get them.

Settings and undo logs live in `%LOCALAPPDATA%\SpaceSweep`.

---

## Project structure

```
spacesweep/
  api.py         methods the UI calls (pywebview js_api / HTTP bridge)
  cleanup.py     cleanup catalogue: what each item is, risk group, what happens if deleted
  scanner.py     parallel disk scan + drill-down tree
  analyzer.py    personal-folder analysis and leftover detection
  organizer.py   Downloads-by-type and photos-by-date plans, apply and undo
  duplicates.py  3-stage exact duplicate finder
  fsutil.py      fast walking, safe deletion, protected paths
  winapi.py      ctypes wrappers: drives, Recycle Bin, known folders, UAC
  jobs.py        background jobs with progress and cancel
  server.py      --browser mode (localhost only, per-run token)
  ui/            index.html, app.css, app.js, i18n.js, logo.svg
tests/           unit tests (temp folders only)
```

Run the tests with `python -m unittest discover -s tests -v`.

---

## Design choices

- **Only one dependency (`pywebview`).** Windows APIs go through `ctypes` (no pywin32), hashing uses `hashlib.blake2b`, and EXIF dates are read by a 60-line parser (no Pillow). The UI has no framework, no CDN and no web fonts, so it works offline and the build stays small.
- **Explain, then act.** Every item carries a *what it is* and a *what happens if you delete it* text. Things SpaceSweep can't safely delete (WSL disks, restore points, `WinSxS`) are explained and linked to the right Windows tool instead of being touched.
- **Browser mode is locked down.** It listens on `127.0.0.1` only, checks the `Host` header and requires a random per-run token on every API call, so other websites can't drive it.

---

## Creator

Created by EtchTechnologies ([Rikion](https://github.com/Trukitro)).

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
