$ErrorActionPreference = "Stop"

$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Repo ".venv\Scripts\python.exe"

if (!(Test-Path -LiteralPath $Python)) {
    python -m venv (Join-Path $Repo ".venv")
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $Repo "requirements.txt")
& $Python -m pip install "fastapi>=0.100" "uvicorn>=0.23" "pydantic>=2.0" "playwright>=1.40.0"
& $Python -m pip install pyinstaller

$BasePrefix = & $Python -c "import sys; print(sys.base_prefix)"
$CondaBin = Join-Path $BasePrefix "Library\bin"
$BinaryArgs = @()
foreach ($Dll in @("tcl86t.dll", "tk86t.dll", "sqlite3.dll", "libbz2.dll", "ffi.dll")) {
    $DllPath = Join-Path $CondaBin $Dll
    if (Test-Path -LiteralPath $DllPath) {
        $BinaryArgs += "--add-binary"
        $BinaryArgs += "$DllPath;."
    }
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "DouyinDownloader" `
    --collect-all aiohttp `
    --collect-all aiosqlite `
    --collect-all rich `
    --collect-all yaml `
    --collect-all fastapi `
    --collect-all uvicorn `
    --collect-all pydantic `
    --collect-all playwright `
    --hidden-import tkinter `
    --hidden-import cli.main `
    --hidden-import core `
    --hidden-import core.preview_service `
    --hidden-import auth `
    --hidden-import config `
    --hidden-import control `
    --hidden-import storage `
    --hidden-import utils `
    --hidden-import tools `
    --hidden-import server `
    --hidden-import gui `
    --hidden-import gui.app `
    --hidden-import gui.controller `
    --hidden-import gui.theme `
    --hidden-import gui.widgets `
    --hidden-import gui.widgets.settings_tab `
    --hidden-import gui.widgets.link_tab `
    --hidden-import gui.widgets.search_tab `
    --hidden-import gui.widgets.preview_tab `
    --hidden-import gui.widgets.log_tab `
    --hidden-import gui.widgets.progress `
    --hidden-import gui.widgets.history_tab `
    @BinaryArgs `
    (Join-Path $Repo "desktop_app.py")

Write-Host ""
Write-Host "Build complete:"
Write-Host (Join-Path $Repo "dist\DouyinDownloader\DouyinDownloader.exe")
