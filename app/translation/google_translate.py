"""Free Google Translate service integration with batching and LaTeX formula preservation."""

import re
import urllib.parse
import httpx
from typing import List, Optional
from app.utils.logging import get_logger

logger = get_logger("GoogleTranslateService")

class GoogleTranslateService:
    """Free Google Translate web API wrapper with automatic chunking and fallback."""

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self.endpoint = "https://translate.googleapis.com/translate_a/single"

    def _split_text_chunks(self, text: str, max_chars: int = 900) -> List[str]:
        """
        Splits text into chunks of at most max_chars without breaking
        protected formula tokens (__SCIDOC_...__).
        """
        if len(text) <= max_chars:
            return [text]

        chunks = []
        # First split by paragraphs / newlines
        paragraphs = text.split("\n")
        current_chunk = []
        current_len = 0

        for para in paragraphs:
            para_len = len(para) + 1
            if current_len + para_len <= max_chars:
                current_chunk.append(para)
                current_len += para_len
            else:
                # Paragraph itself is too large, split by sentence boundary
                if current_chunk:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = []
                    current_len = 0

                if len(para) <= max_chars:
                    current_chunk.append(para)
                    current_len = len(para)
                else:
                    # Split sentences (. , ! , ? )
                    sentences = re.split(r"(?<=[.!?])\s+", para)
                    sub_chunk = []
                    sub_len = 0
                    for sent in sentences:
                        if sub_len + len(sent) + 1 <= max_chars:
                            sub_chunk.append(sent)
                            sub_len += len(sent) + 1
                        else:
                            if sub_chunk:
                                chunks.append(" ".join(sub_chunk))
                                sub_chunk = []
                                sub_len = 0
                            # Hard split if a single token/word is somehow massive
                            if len(sent) > max_chars:
                                for i in range(0, len(sent), max_chars):
                                    chunks.append(sent[i:i + max_chars])
                            else:
                                sub_chunk.append(sent)
                                sub_len = len(sent)
                    if sub_chunk:
                        chunks.append(" ".join(sub_chunk))

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return chunks if chunks else [text]

    def _translate_single_chunk(self, chunk: str, s_lang: str, t_lang: str) -> str:
        """Translates a single chunk (<= 900 chars)."""
        if not chunk or not chunk.strip():
            return chunk

        params = {
            "client": "gtx",
            "sl": s_lang,
            "tl": t_lang,
            "dt": "t",
            "q": chunk
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(self.endpoint, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                        translated_segments = []
                        for segment in data[0]:
                            if isinstance(segment, list) and len(segment) > 0 and segment[0]:
                                translated_segments.append(str(segment[0]))
                        return "".join(translated_segments)
                else:
                    logger.warning(f"Google Translate returned status {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"Google Translate chunk request failed: {e}")

        return chunk

    def translate_text(self, text: str, source_lang: str = "auto", target_lang: str = "vi") -> str:
        """
        Translates text using Google Translate free endpoint with automatic chunking.
        Preserves special placeholder tokens (e.g. __SCIDOC_MATH_0__).
        """
        if not text or not text.strip():
            return text

        s_lang = "auto" if source_lang in ("auto", "en-US", "en-GB") else source_lang
        t_lang = target_lang

        chunks = self._split_text_chunks(text, max_chars=900)
        translated_chunks = []

        for ch in chunks:
            trans_ch = self._translate_single_chunk(ch, s_lang, t_lang)
            translated_chunks.append(trans_ch)

        return "\n".join(translated_chunks) if len(chunks) > 1 and "\n" in text else "".join(translated_chunks)
