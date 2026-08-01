# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = [('C:\\Users\\whoca\\anaconda3\\Library\\bin\\tcl86t.dll', '.'), ('C:\\Users\\whoca\\anaconda3\\Library\\bin\\tk86t.dll', '.'), ('C:\\Users\\whoca\\anaconda3\\Library\\bin\\sqlite3.dll', '.'), ('C:\\Users\\whoca\\anaconda3\\Library\\bin\\libbz2.dll', '.'), ('C:\\Users\\whoca\\anaconda3\\Library\\bin\\ffi.dll', '.')]
hiddenimports = ['tkinter', 'cli.main', 'core', 'core.preview_service', 'auth', 'config', 'control', 'storage', 'utils', 'tools', 'server', 'gui', 'gui.app', 'gui.controller', 'gui.theme', 'gui.widgets', 'gui.widgets.settings_tab', 'gui.widgets.link_tab', 'gui.widgets.search_tab', 'gui.widgets.preview_tab', 'gui.widgets.log_tab', 'gui.widgets.progress', 'gui.widgets.history_tab']
tmp_ret = collect_all('aiohttp')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('aiosqlite')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('rich')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('yaml')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('fastapi')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('uvicorn')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pydantic')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('playwright')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:\\Workspace\\Code Apply\\douyin-downloader\\desktop_app.py'],
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
    icon='C:\\Workspace\\Code Apply\\douyin-downloader\\img\\app_icon.ico',
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
