"""LM Studio local AI provider integration with unified generate method."""

import httpx
from typing import List, Optional
from app.ai.base import AIProvider
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

    def generate(
        self,
        prompt: str = "",
        system_prompt: str = "",
        image_bytes: Optional[bytes] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096
    ) -> str:
        """Single unified core LLM call for LM Studio (text & vision)."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if image_bytes:
            opt_bytes, mime_type = optimize_image_for_ai(image_bytes, max_dim=1800, quality=88)
            base64_img = image_bytes_to_base64(opt_bytes)
            user_content = [
                {"type": "text", "text": prompt or "Process this image."},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_img}"}}
            ]
            messages.append({"role": "user", "content": user_content})
        else:
            messages.append({"role": "user", "content": prompt})

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
                return strip_thought_content(content)
        except Exception as e:
            logger.error(f"LM Studio generation error: {e}")
            raise AIProviderError(f"LM Studio generation failed: {e}")
