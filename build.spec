# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

project_dir = Path.cwd()

datas = [
    (str(project_dir / "assets"), "assets"),
]

hiddenimports = [
    "PySide6",
    "fitz",
    "sympy",
    "httpx",
    "reportlab",
    "markdown_it",
    "app.core.blocks",
    "app.core.document",
    "app.core.pipeline",
    "app.pdf.analyzer",
    "app.pdf.extractor",
    "app.pdf.renderer",
    "app.ocr.local_ocr",
    "app.ocr.formula_ocr",
    "app.ocr.table_ocr",
    "app.layout.ordering",
    "app.ai.router",
    "app.ai.lmstudio",
    "app.ai.online",
    "app.translation.translator",
    "app.latex.generator",
    "app.latex.compiler",
]

a = Analysis(
    ['app/main.py'],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SciDocOCR',
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
    icon='assets/app_icon.ico',
)
