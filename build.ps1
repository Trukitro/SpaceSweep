# Builds SpaceSweep with PyInstaller inside an isolated virtual environment (.build-venv),
# so only pywebview ends up in the .exe and your global Python is never modified.
#   .\build.ps1            -> dist\SpaceSweep\SpaceSweep.exe (folder build, fastest start-up)
#   .\build.ps1 -OneFile   -> dist\SpaceSweep.exe (single file)
param([switch]$OneFile)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venv = Join-Path $PSScriptRoot ".build-venv"
$py = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $py)) {
    python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create $venv" }
}
& $py -m pip install --disable-pip-version-check -q pyinstaller -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Could not install build tools into $venv" }

# The .ico is generated from the same geometry as spacesweep/ui/logo.svg (the only logo kept in the repo).
$icon = Join-Path $venv "SpaceSweep.ico"
& $py tools\make_icon.py $icon
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed" }

$mode = if ($OneFile) { "--onefile" } else { "--onedir" }
& $py -m PyInstaller --noconfirm --clean --windowed $mode `
    --name SpaceSweep `
    --icon $icon `
    --add-data "spacesweep/ui;spacesweep/ui" `
    --exclude-module tkinter `
    SpaceSweep.pyw
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Write-Host "Done: dist\SpaceSweep" -ForegroundColor Green
