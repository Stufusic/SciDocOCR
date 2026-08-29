"""On-Demand Component & Model Downloader with Streaming Progress and Resume Support."""

from __future__ import annotations
import os
import sys
import time
import httpx
from pathlib import Path
from typing import Optional, Callable, Dict, Any
from app.utils.logging import get_logger

logger = get_logger("ModelDownloader")

# Predefined Official CDN & HuggingFace Mirror URLs for On-Demand Models
OFFICIAL_MODELS: Dict[str, Dict[str, Any]] = {
    "yolov10_doclayout": {
        "name": "YOLOv10 DocLayout ONNX (Medium - SOTA)",
        "size_mb": 62.5,
        "filename": "yolov8_layout.onnx",
        "urls": [
            "https://huggingface.co/Oblix/yolov10m-doclaynet_ONNX_document-layout-analysis/resolve/main/onnx/model.onnx",
            "https://hf-mirror.com/Oblix/yolov10m-doclaynet_ONNX_document-layout-analysis/resolve/main/onnx/model.onnx",
            "https://huggingface.co/Oblix/yolov10b-doclaynet_ONNX_document-layout-analysis/resolve/main/onnx/model.onnx"
        ],
        "description": "Model nhận diện bố cục tài liệu & công thức toán học SOTA trên CPU"
    }
}

def get_default_model_dir() -> Path:
    """Returns the default directory for storing downloaded ONNX models."""
    app_root = Path(__file__).resolve().parent.parent.parent
    model_dir = app_root / "assets" / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    return model_dir

def is_model_installed(model_key: str = "yolov10_doclayout") -> bool:
    """Checks if a specified model is already present locally."""
    meta = OFFICIAL_MODELS.get(model_key)
    if not meta:
        return False
    
    target_file = get_default_model_dir() / meta["filename"]
    if target_file.exists() and target_file.stat().st_size > 1_000_000:
        return True
    
    # Check user home directory fallback
    home_file = Path.home() / ".scidoc" / "models" / meta["filename"]
    return home_file.exists() and home_file.stat().st_size > 1_000_000

def download_model_streaming(
    model_key: str = "yolov10_doclayout",
    dest_path: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, int, float, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None
) -> Tuple[bool, str]:
    """
    Downloads model weights with streaming progress callback:
    progress_callback(downloaded_bytes, total_bytes, speed_mb_s, status_text)
    
    Returns: (success, result_message_or_path)
    """
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
                                elapsed = max(0.001, now - start_time)
                                speed_mb = (downloaded / (1024 * 1024)) / elapsed
                                pct = int((downloaded / total_bytes) * 100) if total_bytes > 0 else 0
                                status_str = f"Đang tải {meta['name']}: {downloaded // (1024*1024)}MB / {total_bytes // (1024*1024)}MB ({speed_mb:.1f} MB/s)"
                                
                                if progress_callback:
                                    progress_callback(downloaded, total_bytes, speed_mb, status_str)
                                last_update = now

                    # Validate downloaded file size
                    if temp_file.exists() and temp_file.stat().st_size > 1_000_000:
                        if out_file.exists():
                            out_file.unlink()
                        temp_file.rename(out_file)
                        logger.info(f"Model successfully saved to: {out_file}")
                        return (True, str(out_file))

        except Exception as e:
            logger.warning(f"Failed download from {url}: {e}")
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)

    return (False, "Không thể kết nối đến các máy chủ tải model. Vui lòng kiểm tra lại đường truyền mạng.")
