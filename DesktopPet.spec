# -*- mode: python ; coding: utf-8 -*-


import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

# PyInstaller searches PATH for dependent DLLs. Other installed tools may ship
# incompatible copies of Windows libraries (e.g. ICU); do not bundle those.
if sys.platform == 'win32':
    windows = Path(os.environ.get('SystemRoot', 'C:/Windows'))
    os.environ['PATH'] = os.pathsep.join(map(str, (
        Path(sys.executable).parent, windows / 'System32', windows,
    )))

a = Analysis(
    ['desktop_pet.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=collect_submodules('behaviors'),
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
    name='DesktopPet',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DesktopPet',
)
