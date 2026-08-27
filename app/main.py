"""SciDoc OCR Application Entry Point."""

import sys
import os
from pathlib import Path

# Add project root to sys.path
app_root = Path(__file__).resolve().parent.parent
if str(app_root) not in sys.path:
    sys.path.insert(0, str(app_root))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from app.gui.main_window import MainWindow
from app.utils.logging import setup_logger

def main():
    # Setup application logging
    logger = setup_logger("SciDocOCR")
    logger.info("Starting SciDoc OCR Studio...")

    # Enable native taskbar icon on Windows
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("scidoc.ocr.studio.1.0")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("SciDoc OCR")
    app.setOrganizationName("SciDocStudio")

    # Set Book App Icon
    icon_path = app_root / "assets" / "app_icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Set default app font AFTER QApplication to avoid point-size -1 warnings
    default_font = QFont("Segoe UI", 10)
    if default_font.pointSize() <= 0:
        default_font.setPointSize(10)
    app.setFont(default_font)

    window = MainWindow()
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
