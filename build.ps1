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

$mode = if ($OneFile) { "--onefile" } else { "--onedir" }
& $py -m PyInstaller --noconfirm --clean --windowed $mode `
    --name SpaceSweep `
    --add-data "spacesweep/ui;spacesweep/ui" `
    --exclude-module tkinter `
    SpaceSweep.pyw
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Write-Host "Done: dist\SpaceSweep" -ForegroundColor Green
