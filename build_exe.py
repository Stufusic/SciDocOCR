"""Automated PyInstaller Packaging Script for SciDoc OCR."""

import subprocess
import sys
from pathlib import Path

def build_executable():
    root = Path(__file__).resolve().parent
    spec_file = root / "build.spec"

    print("========================================")
    print("  SciDoc OCR Packaging to SciDocOCR.exe")
    print("========================================")

    if not spec_file.exists():
        print(f"Error: Spec file {spec_file} not found!")
        sys.exit(1)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        str(spec_file)
    ]

    print(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(root))
    if res.returncode == 0:
        print("\n[SUCCESS] Executable built successfully at dist/SciDocOCR.exe")
    else:
        print(f"\n[FAILED] PyInstaller exited with code {res.returncode}")
        sys.exit(res.returncode)

if __name__ == "__main__":
    build_executable()
