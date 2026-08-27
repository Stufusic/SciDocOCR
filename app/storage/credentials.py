"""Secure credentials manager."""

import json
import base64
from pathlib import Path
from typing import Optional, Dict
from app.utils.paths import get_app_dir

class CredentialsManager:
    """Manages sensitive API credentials."""

    def __init__(self, cred_file: Optional[Path] = None):
        self.file_path = cred_file or get_app_dir() / ".credentials"

    def _encode(self, val: str) -> str:
        return base64.b64encode(val.encode("utf-8")).decode("utf-8")

    def _decode(self, enc: str) -> str:
        try:
            return base64.b64decode(enc.encode("utf-8")).decode("utf-8")
        except Exception:
            return ""

    def save_api_key(self, provider: str, key: str) -> None:
        data = self._read_raw()
        data[provider] = self._encode(key)
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def get_api_key(self, provider: str) -> str:
        data = self._read_raw()
        enc = data.get(provider, "")
        return self._decode(enc)

    def mask_key(self, key: str) -> str:
        if not key or len(key) < 8:
            return "***"
        return f"{key[:3]}...{key[-4:]}"

    def _read_raw(self) -> Dict[str, str]:
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
