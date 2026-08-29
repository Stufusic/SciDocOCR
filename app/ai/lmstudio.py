"""LM Studio local AI provider integration with disabled thinking and increased client timeout."""

import re
import httpx
from typing import List, Optional
from app.ai.base import AIProvider
from app.ai.prompts import PROMPT_PROOFREAD_OCR, PROMPT_FORMULA_REPAIR, PROMPT_TRANSLATION, PROMPT_DOCUMENT_TO_MARKDOWN, PROMPT_VISION_OCR_PAGE
from app.core.exceptions import AIProviderError
from app.utils import get_logger, strip_thought_content, optimize_image_for_ai, image_bytes_to_base64

logger = get_logger("LMStudioProvider")

class LMStudioProvider(AIProvider):
    """Integrates with local LM Studio OpenAI-compatible endpoint with thinking disabled."""

    def __init__(self, base_url: str = "http://127.0.0.1:1234/v1", model_name: str = "qwen/qwen3.5-9b", timeout: float = 180.0):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            with httpx.Client(timeout=3.0) as client:
                r = client.get(f"{self.base_url}/models")
                return r.status_code == 200
        except Exception:
            return False

    def complete(self, prompt: str, system_prompt: str = "", temperature: float = 0.1, max_tokens: int = 2048) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Explicitly disable thinking / reasoning for Qwen 3.5 / DeepSeek / LM Studio models
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "enable_thinking": False,
            "chat_template_kwargs": {"enable_thinking": False},
            "reasoning_effort": "low"
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(f"{self.base_url}/chat/completions", json=payload)
                if resp.status_code != 200:
                    raise AIProviderError(f"LM Studio returned error {resp.status_code}: {resp.text}")
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    return ""
                content = choices[0].get("message", {}).get("content", "").strip()

                # Clean any lingering thinking blocks (<think>...</think>, thoughts, etc.)
                return strip_thought_content(content)
        except Exception as e:
            logger.error(f"LM Studio completion error: {e}")
            raise AIProviderError(f"LM Studio completion failed: {e}")

    def correct_text(self, text: str) -> str:
        return self.complete(prompt=text, system_prompt=PROMPT_PROOFREAD_OCR)

    def repair_formula(self, latex: str, issues: List[str]) -> str:
        issues_str = "\n".join(f"- {issue}" for issue in issues)
        prompt = f"Formula:\n```latex\n{latex}\n```\n\nDetected issues:\n{issues_str}"
        return self.complete(prompt=prompt, system_prompt=PROMPT_FORMULA_REPAIR)

    def translate_text(self, text: str, source_lang: str = "en", target_lang: str = "vi") -> str:
        sys_prompt = PROMPT_TRANSLATION.format(source_lang=source_lang, target_lang=target_lang)
        return self.complete(prompt=text, system_prompt=sys_prompt)

    def document_to_markdown(self, page_content: str) -> str:
        return self.complete(prompt=page_content, system_prompt=PROMPT_DOCUMENT_TO_MARKDOWN, max_tokens=4096)

    def ocr_image_to_markdown(self, image_bytes: bytes, raw_text_hint: str = "") -> str:
        """Sends image to LM Studio vision model or falls back to text transcription."""
        if not image_bytes:
            return self.document_to_markdown(raw_text_hint)

        optimized_bytes, mime_type = optimize_image_for_ai(image_bytes, max_dim=1800, quality=88)
        base64_img = image_bytes_to_base64(optimized_bytes)

        try:
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": PROMPT_VISION_OCR_PAGE},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Transcribe this scientific document page to Markdown with accurate LaTeX math and tables."},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime_type};base64,{base64_img}"}
                            }
                        ]
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 4096,
                "enable_thinking": False
            }
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(f"{self.base_url}/chat/completions", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        raw_res = choices[0].get("message", {}).get("content", "").strip()
                        return strip_thought_content(raw_res)
        except Exception as e:
            logger.warning(f"LM Studio Vision OCR failed: {e}")

        return self.document_to_markdown(raw_text_hint)
