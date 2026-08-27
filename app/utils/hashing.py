"""Hashing utilities for SciDoc OCR (SHA-256 caching & integrity)."""

import hashlib
from typing import Union

def compute_file_sha256(file_path: str) -> str:
    """Calculates SHA-256 checksum of a file."""
    sha = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        return sha.hexdigest()
    except Exception:
        return ""

def compute_bytes_sha256(data: bytes) -> str:
    """Calculates SHA-256 checksum of a byte buffer."""
    return hashlib.sha256(data).hexdigest()

def compute_text_sha256(text: str) -> str:
    """Calculates SHA-256 checksum of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
