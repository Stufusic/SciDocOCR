"""Central Common Utilities for SciDoc OCR.
Consolidates reusable helper functions across paths, files, images, hashing, text cleaning, and logging.
"""

import io
import os
import re
import json
import base64
import shutil
import hashlib
import logging
from pathlib import Path
from typing import Union, Optional, Tuple, Any, Dict, List

# =============================================================================
# 1. Path & Directory Helpers
# =============================================================================

def get_app_dir() -> Path:
    """Returns the root directory of the application."""
    return Path(__file__).resolve().parent.parent.parent


def get_cache_dir() -> Path:
    """Returns and ensures the local cache directory."""
    cache = get_app_dir() / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def get_logs_dir() -> Path:
    """Returns and ensures the application logs directory."""
    logs = get_app_dir() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs


def get_assets_dir() -> Path:
    """Returns and ensures the application assets directory."""
    assets = get_app_dir() / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    return assets


def get_projects_dir() -> Path:
    """Returns and ensures the user home projects directory (~/.scidoc_projects)."""
    p = Path.home() / ".scidoc_projects"
    p.mkdir(parents=True, exist_ok=True)
    return p


def ensure_dir(path: Union[str, Path]) -> Path:
    """Ensures that a directory exists, creating all missing parent folders."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def sanitize_filename(name: str, fallback: str = "document") -> str:
    """Sanitizes strings for safe cross-platform folder and file naming."""
    if not name:
        return fallback
    clean = re.sub(r'[\\/*?:"<>|\r\n\t]', "_", name).strip(" ._")
    return clean if clean else fallback


def purge_directory(dir_path: Union[str, Path], keep_root: bool = True) -> None:
    """Safely cleans out all contents inside a directory."""
    p = Path(dir_path)
    if not p.exists():
        return
    for item in p.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            elif item.is_file():
                item.unlink(missing_ok=True)
        except Exception:
            pass
    if not keep_root:
        try:
            p.rmdir()
        except Exception:
            pass


# =============================================================================
# 2. File I/O Helpers
# =============================================================================

def safe_read_text(path: Union[str, Path], default: str = "", encoding: str = "utf-8") -> str:
    """Reads a text file safely with fallback on error."""
    p = Path(path)
    if not p.exists() or not p.is_file():
        return default
    try:
        with open(p, "r", encoding=encoding, errors="replace") as f:
            return f.read()
    except Exception:
        return default


def safe_write_text(path: Union[str, Path], content: str, encoding: str = "utf-8") -> bool:
    """Writes text to a file safely, creating parent folders automatically."""
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding=encoding) as f:
            f.write(content)
        return True
    except Exception:
        return False


def safe_read_json(path: Union[str, Path], default: Any = None) -> Any:
    """Reads and parses a JSON file safely."""
    p = Path(path)
    if not p.exists() or not p.is_file():
        return default
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def safe_write_json(path: Union[str, Path], data: Any, indent: int = 2) -> bool:
    """Serializes data to a JSON file safely with UTF-8 encoding."""
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        return True
    except Exception:
        return False


# =============================================================================
# 3. Image & Base64 Processing
# =============================================================================

def optimize_image_for_ai(
    image_bytes: bytes,
    max_dim: int = 1800,
    quality: int = 88
) -> Tuple[bytes, str]:
    """
    Optimizes raw image bytes (reducing 10MB+ PNGs to ~250KB JPEG)
    for fast network transmission and optimal Vision AI recognition.
    """
    if not image_bytes:
        return b"", "image/png"

    try:
        from PIL import Image
        pil_img = Image.open(io.BytesIO(image_bytes))

        # Downscale oversized images while maintaining aspect ratio
        if max(pil_img.size) > max_dim:
            pil_img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        if pil_img.mode in ("RGBA", "P"):
            pil_img = pil_img.convert("RGB")

        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return image_bytes, "image/png"


def image_bytes_to_base64(image_bytes: bytes) -> str:
    """Converts binary image bytes to a UTF-8 base64 string."""
    if not image_bytes:
        return ""
    return base64.b64encode(image_bytes).decode("utf-8")


def image_file_to_base64_data_uri(file_path: Union[str, Path]) -> str:
    """Reads an image file and formats it as an inline Data URI (data:image/...;base64,...)."""
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return ""
    try:
        suffix = p.suffix.lower().lstrip(".")
        mime = "image/jpeg" if suffix in ("jpg", "jpeg") else f"image/{suffix or 'png'}"
        with open(p, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime};base64,{b64_data}"
    except Exception:
        return ""


# =============================================================================
# 4. AI & Text Cleaning
# =============================================================================

def strip_thought_content(text: str) -> str:
    """
    Strips internal thoughts, reasoning blocks, and CoT traces generated by models
    like DeepSeek-R1, Qwen-Thinking, Claude 3.7 Thinking, or Gemini 2.0/3.5 Thinking.
    """
    if not text:
        return ""

    res = text

    # 1. Standard closed XML tags: <think>...</think>, <thought>...</thought>
    res = re.sub(r"<(think|thought)>[\s\S]*?</\1>", "", res, flags=re.IGNORECASE)

    # 2. Unclosed think/thought tags
    res = re.sub(r"<(think|thought)>[\s\S]*$", "", res, flags=re.IGNORECASE)

    # 3. Fenced thought blocks: ```thought ... ``` or ```think ... ```
    res = re.sub(r"```(thought|think)[\s\S]*?```", "", res, flags=re.IGNORECASE)

    # 4. Leading Thinking Process / Thought headers
    res = re.sub(r"^\s*(\*+)?(Thinking Process|Reasoning Process|Thought):?(\*+)?[\s\S]*?\n\n", "", res, flags=re.IGNORECASE)

    # 5. Bracketed thinking: [Thinking: ...]
    res = re.sub(r"\[(Thinking|Thought|Reasoning):[\s\S]*?\]", "", res, flags=re.IGNORECASE)

    return res.strip()


def clean_latex_math(latex: str) -> str:
    """Cleans common LaTeX math syntax inconsistencies."""
    if not latex:
        return ""
    cleaned = latex.strip()
    # Normalize double dollar signs
    cleaned = re.sub(r"\$\$\s*", "$$", cleaned)
    return cleaned


# =============================================================================
# 5. Hashing & Checksums
# =============================================================================

def compute_file_sha256(file_path: Union[str, Path]) -> str:
    """Calculates SHA-256 checksum of a file efficiently in chunks."""
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return ""
    sha = hashlib.sha256()
    try:
        with open(p, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        return sha.hexdigest()
    except Exception:
        return ""


def compute_bytes_sha256(data: bytes) -> str:
    """Calculates SHA-256 checksum of a byte buffer."""
    return hashlib.sha256(data).hexdigest()


def compute_text_sha256(text: str) -> str:
    """Calculates SHA-256 checksum of a UTF-8 text string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# =============================================================================
# 6. Logging Helpers
# =============================================================================

def get_logger(name: str) -> logging.Logger:
    """Returns a configured logger with standard formatting."""
    from app.utils.logging import get_logger as _get_logger
    return _get_logger(name)
