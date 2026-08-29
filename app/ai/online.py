"""Online AI provider integration supporting OpenAI, Google Gemini, Anthropic Claude, and OpenCode/OpenRouter."""

import re
import httpx
from typing import List, Optional, Dict
from app.ai.base import AIProvider
from app.ai.prompts import PROMPT_PROOFREAD_OCR, PROMPT_FORMULA_REPAIR, PROMPT_TRANSLATION, PROMPT_DOCUMENT_TO_MARKDOWN
from app.core.exceptions import AIProviderError
from app.utils import get_logger, strip_thought_content, optimize_image_for_ai, image_bytes_to_base64

logger = get_logger("OnlineProvider")

# Curated fallback model cascades for rapid failover when quota is exceeded (429) or call errors
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
    
    # Deduplicate while preserving order
    result = []
    for m in candidates:
        if m and m not in result:
            result.append(m)
    return result

class OnlineProvider(AIProvider):
    """Integrates with Online AI providers with automatic rapid failover across model cascades."""

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
        """Returns models to try with previously failed models placed at the end of the line."""
        all_candidates = get_model_cascade_for_provider(self.provider, self.model_name)
        working = [m for m in all_candidates if m not in self._failed_models]
        failed = [m for m in all_candidates if m in self._failed_models]
        return working + failed

    def _on_model_success(self, model_cand: str):
        """Removes model from failed set and rotates active model to working one for subsequent calls."""
        self._failed_models.discard(model_cand)
        if self.model_name != model_cand:
            logger.info(f"OnlineProvider: Successfully rotated active model from '{self.model_name}' to '{model_cand}'.")
            self.model_name = model_cand

    def _on_model_failure(self, model_cand: str, err_desc: str):
        """Marks model as failed to skip it on future calls until working models are exhausted."""
        self._failed_models.add(model_cand)
        logger.warning(f"OnlineProvider: Model '{model_cand}' failed ({err_desc}). Deprioritizing for future calls...")

    def complete(self, prompt: str, system_prompt: str = "", temperature: float = 0.1, max_tokens: int = 2048) -> str:
        if not self.api_key:
            raise AIProviderError(f"{self.provider.capitalize()} API key is missing.")

        models_to_try = self._get_ordered_models_to_try()
        fast_timeout = min(self.timeout, 22.0)  # Rapid failover timeout per model
        last_error = "Unknown error"

        for model_idx, model_cand in enumerate(models_to_try):
            # -------------------------------------------------------------
            # 1. ANTHROPIC CLAUDE API (/v1/messages)
            # -------------------------------------------------------------
            if self.provider == "anthropic":
                headers = {
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model_cand,
                    "messages": [{"role": "user", "content": prompt}],
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
                                from app.utils.thought_cleaner import strip_thought_content
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
            # 2. GOOGLE GEMINI (OpenAI endpoint + Native REST fallback)
            # -------------------------------------------------------------
            elif self.provider == "google":
                # Step A: Try OpenAI-compatible endpoint
                openai_gemini_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "x-goog-api-key": self.api_key,
                    "Content-Type": "application/json"
                }
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                payload = {
                    "model": model_cand,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }

                try:
                    with httpx.Client(timeout=fast_timeout) as client:
                        resp = client.post(openai_gemini_url, json=payload, headers=headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            choices = data.get("choices", [])
                            if choices:
                                raw_res = choices[0].get("message", {}).get("content", "").strip()
                                self._on_model_success(model_cand)
                                from app.utils.thought_cleaner import strip_thought_content
                                return strip_thought_content(raw_res)
                        elif resp.status_code == 429:
                            self._on_model_failure(model_cand, "Gemini quota 429")
                            continue
                except Exception:
                    pass

                # Step B: Native Gemini REST API (generateContent)
                native_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_cand}:generateContent?key={self.api_key}"
                native_headers = {
                    "x-goog-api-key": self.api_key,
                    "Content-Type": "application/json"
                }
                native_payload = {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": f"{system_prompt}\n\n{prompt}" if system_prompt else prompt}]
                        }
                    ],
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": max_tokens
                    }
                }

                try:
                    with httpx.Client(timeout=fast_timeout) as client:
                        resp2 = client.post(native_endpoint, json=native_payload, headers=native_headers)
                        if resp2.status_code == 200:
                            data2 = resp2.json()
                            candidates = data2.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                if parts:
                                    self._on_model_success(model_cand)
                                    from app.utils.thought_cleaner import strip_thought_content
                                    return strip_thought_content(parts[0].get("text", "").strip())
                        elif resp2.status_code == 429:
                            self._on_model_failure(model_cand, "Gemini Native quota 429")
                            continue
                        else:
                            last_error = f"Gemini error {resp2.status_code}: {resp2.text[:200]}"
                            self._on_model_failure(model_cand, last_error)
                            continue
                except Exception as e:
                    last_error = str(e)
                    self._on_model_failure(model_cand, last_error)
                    continue

            # -------------------------------------------------------------
            # 3. OPENAI, OPENCODE, OPENROUTER, CUSTOM
            # -------------------------------------------------------------
            else:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
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
                                from app.utils.thought_cleaner import strip_thought_content
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
        """Sends high-resolution image to Vision AI for complete scientific Markdown transcription."""
        if not image_bytes:
            return self.document_to_markdown(raw_text_hint)

        # Optimize image for fast network upload & vision API decoding
        optimized_bytes, mime_type = optimize_image_for_ai(image_bytes, max_dim=1800, quality=88)
        base64_img = image_bytes_to_base64(optimized_bytes)
        from app.ai.prompts import PROMPT_VISION_OCR_PAGE

        # Multi-model cascade for Vision OCR with failed models placed at the end
        models_to_try = self._get_ordered_models_to_try()
        fast_timeout = min(self.timeout, 25.0)

        # 1. Google Gemini Vision API (with automatic cascade failover across all Gemini models)
        if self.provider == "google":
            for gemini_model in models_to_try:
                try:
                    native_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={self.api_key}"
                    native_headers = {
                        "x-goog-api-key": self.api_key,
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "contents": [
                            {
                                "role": "user",
                                "parts": [
                                    {"text": PROMPT_VISION_OCR_PAGE},
                                    {
                                        "inlineData": {
                                            "mimeType": mime_type,
                                            "data": base64_img
                                        }
                                    }
                                ]
                            }
                        ],
                        "generationConfig": {
                            "temperature": 0.1,
                            "maxOutputTokens": 4096
                        }
                    }
                    with httpx.Client(timeout=fast_timeout) as client:
                        resp = client.post(native_endpoint, json=payload, headers=native_headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            candidates = data.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                if parts:
                                    self._on_model_success(gemini_model)
                                    from app.utils.thought_cleaner import strip_thought_content
                                    return strip_thought_content(parts[0].get("text", "").strip())
                        elif resp.status_code == 429:
                            self._on_model_failure(gemini_model, "Gemini Vision rate limit 429")
                            continue
                except Exception as e:
                    self._on_model_failure(gemini_model, str(e))
                    continue

        # 2. OpenAI / OpenRouter / Custom Vision API
        elif self.provider in ("openai", "openrouter", "opencode", "custom"):
            for cand_model in models_to_try:
                try:
                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": cand_model,
                        "messages": [
                            {"role": "system", "content": PROMPT_VISION_OCR_PAGE},
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "Transcribe this scientific document page to Markdown with accurate LaTeX math and tables."},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:{mime_type};base64,{base64_img}"
                                        }
                                    }
                                ]
                            }
                        ],
                        "temperature": 0.1,
                        "max_tokens": 4096
                    }
                    with httpx.Client(timeout=fast_timeout) as client:
                        resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            choices = data.get("choices", [])
                            if choices:
                                self._on_model_success(cand_model)
                                from app.utils.thought_cleaner import strip_thought_content
                                return strip_thought_content(choices[0].get("message", {}).get("content", "").strip())
                        elif resp.status_code == 429:
                            self._on_model_failure(cand_model, "Vision OCR rate limit 429")
                            continue
                except Exception as e:
                    self._on_model_failure(cand_model, str(e))
                    continue

        # 3. Anthropic Claude Vision API
        elif self.provider == "anthropic":
            for claude_model in models_to_try:
                try:
                    headers = {
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": claude_model,
                        "system": PROMPT_VISION_OCR_PAGE,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": mime_type,
                                            "data": base64_img
                                        }
                                    },
                                    {"type": "text", "text": "Transcribe this page to Markdown with precise LaTeX formulas."}
                                ]
                            }
                        ],
                        "max_tokens": 4096,
                        "temperature": 0.1
                    }
                    with httpx.Client(timeout=fast_timeout) as client:
                        resp = client.post(f"{self.base_url}/messages", json=payload, headers=headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            content_list = data.get("content", [])
                            if content_list:
                                self._on_model_success(claude_model)
                                from app.utils.thought_cleaner import strip_thought_content
                                return strip_thought_content(content_list[0].get("text", "").strip())
                        elif resp.status_code == 429:
                            self._on_model_failure(claude_model, "Claude Vision rate limit 429")
                            continue
                except Exception as e:
                    self._on_model_failure(claude_model, str(e))
                    continue

        # Fallback to text representation
        return self.document_to_markdown(raw_text_hint)
