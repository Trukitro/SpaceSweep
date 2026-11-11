# Builds SpaceSweep with PyInstaller.
#   .\build.ps1            -> dist\SpaceSweep\SpaceSweep.exe (folder build, fastest start-up)
#   .\build.ps1 -OneFile   -> dist\SpaceSweep.exe (single file, unpacks to %TEMP% on each start)
param([switch]$OneFile)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install --upgrade pyinstaller -r requirements.txt

$mode = if ($OneFile) { "--onefile" } else { "--onedir" }
python -m PyInstaller --noconfirm --clean --windowed $mode `
    --name SpaceSweep `
    --add-data "ui;ui" `
    --exclude-module tkinter `
    SpaceSweep.pyw

Write-Host "Done: dist\SpaceSweep" -ForegroundColor Green
