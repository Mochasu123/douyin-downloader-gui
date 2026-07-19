# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for DouyinDownloader GUI.
#
# DLLs (tcl86t.dll, tk86t.dll, etc.) are injected dynamically by
# build_desktop_app.ps1 via --add-binary so this spec stays portable.
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = [
    'tkinter', 'cli.main', 'core', 'core.preview_service', 'auth',
    'config', 'control', 'storage', 'utils', 'tools', 'server',
    'gui', 'gui.app', 'gui.controller', 'gui.theme',
    'gui.widgets', 'gui.widgets.settings_tab', 'gui.widgets.link_tab',
    'gui.widgets.preview_tab', 'gui.widgets.log_tab',
    'gui.widgets.progress', 'gui.widgets.history_tab',
]

for pkg in ('aiohttp', 'aiosqlite', 'rich', 'yaml', 'fastapi', 'uvicorn',
            'pydantic', 'playwright'):
    ret = collect_all(pkg)
    datas += ret[0]
    binaries += ret[1]
    hiddenimports += ret[2]

a = Analysis(
    ['desktop_app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DouyinDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DouyinDownloader',
)
