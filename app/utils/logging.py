"""Application-wide logging configuration."""

import logging
import sys
from pathlib import Path

_root_configured = False

def _configure_root():
    global _root_configured
    if _root_configured:
        return
    try:
        from app.utils.common import get_logs_dir
        logs_dir = get_logs_dir()
    except Exception:
        logs_dir = Path.home() / ".scidoc_logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("SciDocOCR")
    root_logger.setLevel(logging.DEBUG)

    # Prevent duplicate handlers
    if not root_logger.handlers:
        # Console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        console_format = logging.Formatter("[%(levelname)s] %(asctime)s - %(name)s: %(message)s", datefmt="%H:%M:%S")
        ch.setFormatter(console_format)
        root_logger.addHandler(ch)

        # File handler
        try:
            log_path = logs_dir / "scidoc.log"
            fh = logging.FileHandler(str(log_path), encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            file_format = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s")
            fh.setFormatter(file_format)
            root_logger.addHandler(fh)
        except Exception as e:
            print(f"Warning: Could not set up file logger: {e}")

    _root_configured = True

def setup_logger(name: str = "SciDocOCR", log_file: str = "scidoc.log") -> logging.Logger:
    _configure_root()
    return logging.getLogger(name)

def get_logger(name: str = "SciDocOCR") -> logging.Logger:
    """Returns a named logger child of the SciDocOCR logging hierarchy."""
    _configure_root()
    return logging.getLogger(name)
