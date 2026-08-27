"""Builds standalone SciDocOCR-Launcher.exe using PyInstaller."""

import subprocess
import sys
from pathlib import Path

def build():
    root = Path(__file__).resolve().parent
    launcher_script = root / "launcher.py"

    print("==================================================")
    print("  Building SciDocOCR-Launcher.exe (PyInstaller)")
    print("==================================================")

    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--icon", str(root / "assets" / "app_icon.ico"),
        "--add-data", f"{root / 'assets'};assets",
        "--name", "SciDocOCR-Launcher",
        str(launcher_script)
    ]

    print(f"Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(root))
    if res.returncode == 0:
        print("\n[SUCCESS] Launcher executable built at: dist/SciDocOCR-Launcher/SciDocOCR-Launcher.exe")
    else:
        print(f"\n[FAILED] Build exited with code: {res.returncode}")

if __name__ == "__main__":
    build()
