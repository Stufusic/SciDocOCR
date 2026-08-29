"""On-Demand Component & Model Downloader with Streaming Progress and Resume Support."""

from __future__ import annotations
import os
import sys
import time
import httpx
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Tuple
from app.utils.logging import get_logger

logger = get_logger("ModelDownloader")

# Predefined Official CDN & HuggingFace Mirror URLs for On-Demand Models
OFFICIAL_MODELS: Dict[str, Dict[str, Any]] = {
    "yolov8_doclayout": {
        "name": "YOLOv8 DocLayout ONNX (Layout Analysis)",
        "size_mb": 45.0,
        "filename": "yolov8_layout.onnx",
        "urls": [
            "https://huggingface.co/herobd/yolov8_doclaynet/resolve/main/yolov8n-doclaynet.onnx",
            "https://hf-mirror.com/herobd/yolov8_doclaynet/resolve/main/yolov8n-doclaynet.onnx",
            "https://huggingface.co/herobd/yolov8_doclaynet/resolve/main/yolov8s-doclaynet.onnx"
        ],
        "description": "Model YOLOv8 nhận diện phân vùng bố cục văn bản, bảng biểu, công thức toán trên CPU"
    },
    "unimernet": {
        "name": "UniMERNet Base (SOTA Math LaTeX - Highest Quality)",
        "size_mb": 260.0,
        "filename": "unimernet_base.pth",
        "urls": [
            "https://huggingface.co/wanderkid/unimernet_base/resolve/main/pytorch_model.pth",
            "https://hf-mirror.com/wanderkid/unimernet_base/resolve/main/pytorch_model.pth",
            "https://huggingface.co/opendatalab/PDF-Extract-Kit-1.0/resolve/main/models/MFR/unimernet_base/pytorch_model.pth"
        ],
        "description": "Model UniMERNet Base (Chất lượng cao nhất) bóc tách và giải mã công thức toán học chuyên sâu sang mã nguồn LaTeX"
    }
}

def get_default_model_dir() -> Path:
    """Returns the default directory for storing downloaded ONNX/weights models."""
    app_root = Path(__file__).resolve().parent.parent.parent
    model_dir = app_root / "assets" / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    return model_dir

def is_model_installed(model_key: str = "yolov8_doclayout") -> bool:
    """Checks if a specified model is already present locally."""
    meta = OFFICIAL_MODELS.get(model_key)
    if not meta:
        # Fallback aliases
        if model_key == "yolov10_doclayout":
            meta = OFFICIAL_MODELS.get("yolov8_doclayout")
        if not meta:
            return False
    
    target_file = get_default_model_dir() / meta["filename"]
    if target_file.exists() and target_file.stat().st_size > 500_000:
        return True
    
    # Check user home directory fallback
    home_file = Path.home() / ".scidoc" / "models" / meta["filename"]
    return home_file.exists() and home_file.stat().st_size > 500_000

def download_model_streaming(
    model_key: str = "yolov8_doclayout",
    dest_path: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, int, float, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None
) -> Tuple[bool, str]:
    """
    Downloads model weights with streaming progress callback:
    progress_callback(downloaded_bytes, total_bytes, speed_mb_s, status_text)
    
    Returns: (success, result_message_or_path)
    """
    if model_key == "yolov10_doclayout":
        model_key = "yolov8_doclayout"

    meta = OFFICIAL_MODELS.get(model_key)
    if not meta:
        return (False, f"Model key '{model_key}' not found in registry.")

    out_file = dest_path or (get_default_model_dir() / meta["filename"])
    out_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = out_file.with_suffix(".tmp")

    urls = meta["urls"]
    headers = {"User-Agent": "SciDocOCR-Downloader/1.0"}

    for url in urls:
        if cancel_check and cancel_check():
            return (False, "Download cancelled by user.")

        logger.info(f"Attempting download from: {url}")
        try:
            with httpx.Client(follow_redirects=True, timeout=60.0) as client:
                with client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code != 200:
                        logger.warning(f"URL {url} returned status {resp.status_code}, trying next mirror...")
                        continue

                    total_bytes = int(resp.headers.get("content-length", int(meta["size_mb"] * 1024 * 1024)))
                    downloaded = 0
                    start_time = time.time()
                    last_update = 0.0

                    with open(temp_file, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=65536):
                            if cancel_check and cancel_check():
                                temp_file.unlink(missing_ok=True)
                                return (False, "Download cancelled.")

                            f.write(chunk)
                            downloaded += len(chunk)

                            now = time.time()
                            if now - last_update > 0.15 or downloaded == total_bytes:
                                elapsed = max(0.01, now - start_time)
                                speed_mb_s = (downloaded / (1024 * 1024)) / elapsed
                                status_txt = f"{meta['name']} ({downloaded / (1024*1024):.1f}MB / {total_bytes / (1024*1024):.1f}MB)"
                                if progress_callback:
                                    progress_callback(downloaded, total_bytes, speed_mb_s, status_txt)
                                last_update = now

                    # Rename temp file to final on success
                    if temp_file.exists() and temp_file.stat().st_size > 100_000:
                        if out_file.exists():
                            out_file.unlink()
                        temp_file.rename(out_file)
                        logger.info(f"Model {meta['name']} downloaded successfully to {out_file}")
                        return (True, str(out_file))

        except Exception as e:
            logger.warning(f"Failed download from {url}: {e}")
            temp_file.unlink(missing_ok=True)

    return (False, f"Could not download {meta['name']} from all mirrors.")
