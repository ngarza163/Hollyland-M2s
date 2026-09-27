# Builds "dist\Lark M2S Control.exe" (single file, no console window).
# Usage (from this folder):  powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    py -3.12 -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt pyinstaller==6.22.3

& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name "Lark M2S Control" `
    --icon "assets\app.ico" `
    --add-data "assets\icon.png;assets" `
    app.py

Write-Host "Built: $PSScriptRoot\dist\Lark M2S Control.exe"
