"""Online AI provider integration supporting OpenAI, Google Gemini, Anthropic Claude, and OpenCode/OpenRouter."""

import re
import httpx
from typing import List, Optional, Dict, Any
from app.ai.base import AIProvider
from app.core.exceptions import AIProviderError
from app.utils import get_logger, strip_thought_content, optimize_image_for_ai, image_bytes_to_base64

logger = get_logger("OnlineProvider")

FALLBACK_CASCADE: Dict[str, List[str]] = {
    "google": [
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
        "gemini-1.5-pro"
    ],
    "openai": [
        "gpt-4o-mini",
        "gpt-4o",
        "o3-mini",
        "gpt-3.5-turbo"
    ],
    "anthropic": [
        "claude-3-7-sonnet-20250219",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-haiku-20240307"
    ],
    "opencode": [
        "deepseek/deepseek-chat",
        "openai/gpt-4o-mini",
        "google/gemini-2.0-flash-001",
        "qwen/qwen-2.5-72b-instruct",
        "meta-llama/llama-3.3-70b-instruct"
    ],
    "custom": [
        "gpt-4o-mini",
        "gpt-4o",
        "qwen/qwen3.5-9b",
        "deepseek-chat"
    ]
}

def get_model_cascade_for_provider(provider: str, configured_model: str) -> List[str]:
    """Builds an ordered, deduplicated list of fallback models for the given provider."""
    prov = (provider or "openai").lower()
    base_cascade = FALLBACK_CASCADE.get(prov, FALLBACK_CASCADE["openai"])
    configured = (configured_model or "").replace("models/", "").strip()
    
    candidates = []
    if configured:
        candidates.append(configured)
    candidates.extend(base_cascade)
    
    result = []
    for m in candidates:
        if m and m not in result:
            result.append(m)
    return result

class OnlineProvider(AIProvider):
    """Integrates with Online AI providers through a single unified `generate` method with failover."""

    def __init__(
        self,
        provider: str = "openai",
        api_key: str = "",
        base_url: str = "",
        model_name: str = "gpt-4o-mini",
        timeout: float = 60.0
    ):
        from app.ai.model_fetcher import DEFAULT_URLS
        self.provider = (provider or "openai").lower()
        self.api_key = api_key.strip()
        clean_url = (base_url or "").strip()
        self.base_url = (clean_url if clean_url else DEFAULT_URLS.get(self.provider, "https://api.openai.com/v1")).rstrip("/")
        self.model_name = model_name.strip()
        self.timeout = timeout
        self._failed_models: set = set()

    def is_available(self) -> bool:
        """Returns True if an API key is configured."""
        return bool(self.api_key and self.api_key.strip())

    def _get_ordered_models_to_try(self) -> List[str]:
        """Returns models to try with previously failed models placed at the end."""
        all_candidates = get_model_cascade_for_provider(self.provider, self.model_name)
        working = [m for m in all_candidates if m not in self._failed_models]
        failed = [m for m in all_candidates if m in self._failed_models]
        return working + failed

    def _on_model_success(self, model_cand: str):
        """Rotates active model to working one and clears failure mark."""
        self._failed_models.discard(model_cand)
        if self.model_name != model_cand:
            logger.info(f"OnlineProvider: Successfully rotated active model from '{self.model_name}' to '{model_cand}'.")
            self.model_name = model_cand

    def _on_model_failure(self, model_cand: str, err_desc: str):
        """Marks model as failed to skip it on future calls."""
        self._failed_models.add(model_cand)
        logger.warning(f"OnlineProvider: Model '{model_cand}' failed ({err_desc}). Deprioritizing...")

    def generate(
        self,
        prompt: str = "",
        system_prompt: str = "",
        image_bytes: Optional[bytes] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096
    ) -> str:
        """
        Unified single API call handling text, image vision, and system prompt
        with automatic cascade failover across all model candidates.
        """
        if not self.api_key:
            raise AIProviderError(f"{self.provider.capitalize()} API key is missing.")

        # Optimize image if provided
        base64_img = None
        mime_type = "image/jpeg"
        if image_bytes:
            opt_bytes, mime_type = optimize_image_for_ai(image_bytes, max_dim=1800, quality=88)
            base64_img = image_bytes_to_base64(opt_bytes)

        models_to_try = self._get_ordered_models_to_try()
        fast_timeout = min(self.timeout, 25.0)
        last_error = "Unknown error"

        for model_cand in models_to_try:
            # -------------------------------------------------------------
            # 1. ANTHROPIC CLAUDE API
            # -------------------------------------------------------------
            if self.provider == "anthropic":
                headers = {
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                }
                if base64_img:
                    user_content = [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": base64_img
                            }
                        },
                        {"type": "text", "text": prompt or "Process this image."}
                    ]
                else:
                    user_content = prompt

                payload = {
                    "model": model_cand,
                    "messages": [{"role": "user", "content": user_content}],
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
                if system_prompt:
                    payload["system"] = system_prompt

                try:
                    with httpx.Client(timeout=fast_timeout) as client:
                        resp = client.post(f"{self.base_url}/messages", json=payload, headers=headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            content_list = data.get("content", [])
                            if content_list:
                                self._on_model_success(model_cand)
                                return strip_thought_content(content_list[0].get("text", "").strip())
                        elif resp.status_code == 429:
                            self._on_model_failure(model_cand, "Rate limit 429")
                            continue
                        else:
                            last_error = f"Anthropic error {resp.status_code}: {resp.text[:200]}"
                            self._on_model_failure(model_cand, last_error)
                            continue
                except Exception as e:
                    last_error = str(e)
                    self._on_model_failure(model_cand, last_error)
                    continue

            # -------------------------------------------------------------
            # 2. GOOGLE GEMINI API (Native REST generateContent)
            # -------------------------------------------------------------
            elif self.provider == "google":
                native_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_cand}:generateContent?key={self.api_key}"
                native_headers = {
                    "x-goog-api-key": self.api_key,
                    "Content-Type": "application/json"
                }
                parts = []
                if base64_img:
                    parts.append({
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": base64_img
                        }
                    })
                parts.append({"text": prompt or "Process the input."})

                native_payload = {
                    "contents": [{"role": "user", "parts": parts}],
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": max_tokens
                    }
                }
                if system_prompt:
                    native_payload["systemInstruction"] = {
                        "parts": [{"text": system_prompt}]
                    }

                try:
                    with httpx.Client(timeout=fast_timeout) as client:
                        resp = client.post(native_endpoint, json=native_payload, headers=native_headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            candidates = data.get("candidates", [])
                            if candidates:
                                parts_out = candidates[0].get("content", {}).get("parts", [])
                                if parts_out:
                                    self._on_model_success(model_cand)
                                    return strip_thought_content(parts_out[0].get("text", "").strip())
                        elif resp.status_code == 429:
                            self._on_model_failure(model_cand, "Gemini rate limit 429")
                            continue
                        else:
                            last_error = f"Gemini error {resp.status_code}: {resp.text[:200]}"
                            self._on_model_failure(model_cand, last_error)
                            continue
                except Exception as e:
                    last_error = str(e)
                    self._on_model_failure(model_cand, last_error)
                    continue

            # -------------------------------------------------------------
            # 3. OPENAI, OPENROUTER, OPENCODE, CUSTOM API (/chat/completions)
            # -------------------------------------------------------------
            else:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})

                if base64_img:
                    user_content = [
                        {"type": "text", "text": prompt or "Process this image."},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_img}"}}
                    ]
                    messages.append({"role": "user", "content": user_content})
                else:
                    messages.append({"role": "user", "content": prompt})

                payload = {
                    "model": model_cand,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
                if self.provider in ("opencode", "custom"):
                    payload["chat_template_kwargs"] = {"enable_thinking": False}

                try:
                    with httpx.Client(timeout=fast_timeout) as client:
                        resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            choices = data.get("choices", [])
                            if choices:
                                raw_res = choices[0].get("message", {}).get("content", "").strip()
                                self._on_model_success(model_cand)
                                return strip_thought_content(raw_res)
                        elif resp.status_code == 429:
                            self._on_model_failure(model_cand, "Rate limit 429")
                            continue
                        else:
                            last_error = f"{self.provider.capitalize()} error {resp.status_code}: {resp.text[:200]}"
                            self._on_model_failure(model_cand, last_error)
                            continue
                except Exception as e:
                    last_error = str(e)
                    self._on_model_failure(model_cand, last_error)
                    continue

        raise AIProviderError(f"All models for {self.provider.capitalize()} failed. Last error: {last_error}")
