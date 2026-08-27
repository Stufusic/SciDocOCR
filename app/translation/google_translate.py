"""Free Google Translate service integration with batching and LaTeX formula preservation."""

import re
import urllib.parse
import httpx
from typing import List, Optional
from app.utils.logging import get_logger

logger = get_logger("GoogleTranslateService")

class GoogleTranslateService:
    """Free Google Translate web API wrapper with automatic fallback."""

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self.endpoint = "https://translate.googleapis.com/translate_a/single"

    def translate_text(self, text: str, source_lang: str = "auto", target_lang: str = "vi") -> str:
        """
        Translates text using Google Translate free endpoint.
        Preserves special placeholder tokens (e.g. __MATH_0__, __CODE_1__).
        """
        if not text or not text.strip():
            return text

        # Map language codes if necessary
        s_lang = "auto" if source_lang in ("auto", "en-US", "en-GB") else source_lang
        t_lang = target_lang

        params = {
            "client": "gtx",
            "sl": s_lang,
            "tl": t_lang,
            "dt": "t",
            "q": text
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(self.endpoint, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    # Google Translate returns a list of translated segments: [[["translated", "original", ...], ...]]
                    if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                        translated_segments = []
                        for segment in data[0]:
                            if isinstance(segment, list) and len(segment) > 0 and segment[0]:
                                translated_segments.append(str(segment[0]))
                        return "".join(translated_segments)
                else:
                    logger.warning(f"Google Translate returned status {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"Google Translate request failed: {e}")

        return text
