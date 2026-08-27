"""SHA-256 based Caching Engine to prevent redundant OCR and Translation."""

import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from app.utils.paths import get_cache_dir
from app.core.blocks import BaseBlock, block_from_dict

class CacheManager:
    """Manages disk-backed SHA-256 cached results."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or get_cache_dir()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cached_page_blocks(self, page_sha256: str) -> Optional[List[BaseBlock]]:
        if not page_sha256:
            return None
        cache_file = self.cache_dir / f"ocr_{page_sha256}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return [block_from_dict(b) for b in data]
            except Exception:
                return None
        return None

    def store_cached_page_blocks(self, page_sha256: str, blocks: List[BaseBlock]) -> None:
        if not page_sha256:
            return
        cache_file = self.cache_dir / f"ocr_{page_sha256}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump([b.to_dict() for b in blocks], f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get_cached_translation(self, text_sha256: str, target_lang: str) -> Optional[str]:
        cache_file = self.cache_dir / f"trans_{target_lang}_{text_sha256}.txt"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                return None
        return None

    def store_cached_translation(self, text_sha256: str, target_lang: str, translated_text: str) -> None:
        cache_file = self.cache_dir / f"trans_{target_lang}_{text_sha256}.txt"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(translated_text)
        except Exception:
            pass
