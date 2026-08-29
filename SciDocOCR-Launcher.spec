# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\My project\\SciDocOCR\\launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\My project\\SciDocOCR\\assets', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'torchvision', 'torchaudio', 'scipy', 'numba', 'llvmlite', 'mkl', 'sympy', 'fitz', 'PySide6', 'PIL.ImageQt'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SciDocOCR-Launcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:\\My project\\SciDocOCR\\assets\\app_icon.ico'],
)
