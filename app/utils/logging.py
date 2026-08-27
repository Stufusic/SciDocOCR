"""Application-wide logging configuration."""

import logging
import sys
from pathlib import Path
from app.utils.paths import get_logs_dir

_logger = None

def setup_logger(name: str = "SciDocOCR", log_file: str = "scidoc.log") -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    console_format = logging.Formatter("[%(levelname)s] %(asctime)s - %(name)s: %(message)s", datefmt="%H:%M:%S")
    ch.setFormatter(console_format)
    logger.addHandler(ch)

    # File handler
    try:
        log_path = get_logs_dir() / log_file
        fh = logging.FileHandler(str(log_path), encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        file_format = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s")
        fh.setFormatter(file_format)
        logger.addHandler(fh)
    except Exception as e:
        print(f"Warning: Could not set up file logger: {e}")

    _logger = logger
    return logger

def get_logger(name: str = "SciDocOCR") -> logging.Logger:
    global _logger
    if _logger is None:
        return setup_logger(name)
    return _logger
