$ErrorActionPreference = "Stop"

$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path

# 1. Back up user data from dist folder to root before PyInstaller deletes dist/!
foreach ($File in @('config.yml', '.cookies.json', 'dy_downloader.db', 'desktop_settings.json')) {
    $DistFile = Join-Path $Repo "dist\DouyinDownloader\$File"
    $RootFile = Join-Path $Repo $File
    if (Test-Path -LiteralPath $DistFile) {
        Copy-Item -Path $DistFile -Destination $RootFile -Force
        Write-Host "Backed up user data from dist: $File"
    }
}

# 2. Build modern React frontend
Write-Host "Building React frontend..."
Push-Location (Join-Path $Repo "frontend")
try {
    & npm run build
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend build failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

# 3. Ensure Python venv & dependencies
$Python = Join-Path $Repo ".venv\Scripts\python.exe"
if (!(Test-Path -LiteralPath $Python)) {
    python -m venv (Join-Path $Repo ".venv")
}

& $Python -c "import webview, fastapi, uvicorn, websockets, multipart, playwright, PIL, openpyxl, PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -r (Join-Path $Repo "requirements.txt")
    & $Python -m pip install pyinstaller
}

$BasePrefix = & $Python -c "import sys; print(sys.base_prefix)"
$CondaBin = Join-Path $BasePrefix "Library\bin"
$BinaryArgs = @()
foreach ($Dll in @("sqlite3.dll", "libbz2.dll", "ffi.dll")) {
    $DllPath = Join-Path $CondaBin $Dll
    if (Test-Path -LiteralPath $DllPath) {
        $BinaryArgs += "--add-binary"
        $BinaryArgs += "$DllPath;."
    }
}

# 4. Build PyInstaller bundle
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "DouyinDownloader" `
    --collect-all aiohttp `
    --collect-all aiosqlite `
    --collect-all httpx `
    --collect-all rich `
    --collect-all yaml `
    --collect-all fastapi `
    --collect-all uvicorn `
    --collect-all starlette `
    --collect-all websockets `
    --collect-all pydantic `
    --collect-all playwright `
    --collect-all PIL `
    --collect-all openpyxl `
    --collect-all imageio_ffmpeg `
    --collect-all gmssl `
    --collect-all webview `
    --collect-all pythonnet `
    --collect-all clr_loader `
    --collect-all bottle `
    --collect-all proxy_tools `
    --hidden-import cli.main `
    --hidden-import core `
    --hidden-import core.preview_service `
    --hidden-import core.comment_media `
    --hidden-import core.comment_export `
    --hidden-import core.live_photo `
    --hidden-import auth `
    --hidden-import config `
    --hidden-import control `
    --hidden-import storage `
    --hidden-import utils `
    --hidden-import tools `
    --hidden-import server `
    --hidden-import desktop_server `
    --hidden-import desktop_server.app `
    --hidden-import desktop_server.routes `
    --hidden-import desktop_server.state `
    --hidden-import desktop_server.events `
    --hidden-import desktop_server.page_bridge `
    --hidden-import uvicorn.logging `
    --hidden-import uvicorn.loops.auto `
    --hidden-import uvicorn.protocols.http.auto `
    --hidden-import uvicorn.protocols.websockets.auto `
    --hidden-import uvicorn.lifespan.on `
    --add-data "$($Repo)\frontend\dist;frontend/dist" `
    --add-data "$($Repo)\img;img" `
    --add-data "$($Repo)\config.example.yml;." `
    --icon (Join-Path $Repo "img\app_icon.ico") `
    @BinaryArgs `
    (Join-Path $Repo "desktop_app.py")

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Build complete:"
Write-Host (Join-Path $Repo "dist\DouyinDownloader\DouyinDownloader.exe")

# 5. Copy user data back to dist folder
foreach ($File in @('config.yml', '.cookies.json', 'dy_downloader.db', 'desktop_settings.json')) {
    $Src = Join-Path $Repo $File
    if (Test-Path -LiteralPath $Src) {
        Copy-Item -Path $Src -Destination (Join-Path $Repo "dist\DouyinDownloader\$File") -Force
        Write-Host "Restored user data: $File"
    }
}

# 6. Update Desktop Shortcut
$DesktopPath = [Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $DesktopPath 'DouyinDownloader.lnk'
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$ExePath = Join-Path $Repo 'dist\DouyinDownloader\DouyinDownloader.exe'
$Shortcut.TargetPath = $ExePath
$Shortcut.IconLocation = Join-Path $Repo 'img\app_icon.ico'
$Shortcut.WorkingDirectory = Join-Path $Repo 'dist\DouyinDownloader'
$Shortcut.Save()
Write-Host "Updated Desktop Shortcut at $ShortcutPath"

# 7. Run self-test on built executable
Write-Host "Running packaged executable self-test..."
& $ExePath --self-test
if ($LASTEXITCODE -ne 0) {
    throw "Packaged executable self-test failed with exit code $LASTEXITCODE"
}
Write-Host "Self-test PASSED!"
