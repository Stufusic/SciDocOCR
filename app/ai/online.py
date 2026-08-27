"""Online AI provider integration supporting OpenAI, Google Gemini, Anthropic Claude, and OpenCode/OpenRouter."""

import re
import httpx
from typing import List, Optional
from app.ai.base import AIProvider
from app.ai.prompts import PROMPT_PROOFREAD_OCR, PROMPT_FORMULA_REPAIR, PROMPT_TRANSLATION, PROMPT_DOCUMENT_TO_MARKDOWN
from app.core.exceptions import AIProviderError
from app.utils.logging import get_logger

logger = get_logger("OnlineProvider")

class OnlineProvider(AIProvider):
    """Integrates with Online AI providers: OpenAI, Google Gemini, Anthropic Claude, and OpenCode/OpenRouter."""

    def __init__(
        self,
        provider: str = "openai",
        api_key: str = "",
        base_url: str = "",
        model_name: str = "gpt-4o-mini",
        timeout: float = 180.0
    ):
        from app.ai.model_fetcher import DEFAULT_URLS
        self.provider = (provider or "openai").lower()
        self.api_key = api_key.strip()
        clean_url = (base_url or "").strip()
        self.base_url = (clean_url if clean_url else DEFAULT_URLS.get(self.provider, "https://api.openai.com/v1")).rstrip("/")
        self.model_name = model_name.strip()
        self.timeout = timeout

    def is_available(self) -> bool:
        """Returns True if an API key is configured."""
        return bool(self.api_key and self.api_key.strip())

    def complete(self, prompt: str, system_prompt: str = "", temperature: float = 0.1, max_tokens: int = 2048) -> str:
        if not self.api_key:
            raise AIProviderError(f"{self.provider.capitalize()} API key is missing.")

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
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            if system_prompt:
                payload["system"] = system_prompt

            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(f"{self.base_url}/messages", json=payload, headers=headers)
                    if resp.status_code != 200:
                        raise AIProviderError(f"Anthropic API error {resp.status_code}: {resp.text}")
                    data = resp.json()
                    content_list = data.get("content", [])
                    if not content_list:
                        return ""
                    from app.utils.thought_cleaner import strip_thought_content
                    raw_res = content_list[0].get("text", "").strip()
                    return strip_thought_content(raw_res)
            except Exception as e:
                logger.error(f"Anthropic completion error: {e}")
                raise AIProviderError(f"Anthropic request failed: {e}")

        # -------------------------------------------------------------
        # 2. GOOGLE GEMINI (Dual: OpenAI endpoint with fallback to Native REST)
        # -------------------------------------------------------------
        elif self.provider == "google":
            import time
            models_to_try = [
                self.model_name.replace("models/", "").strip(),
                "gemini-2.0-flash",
                "gemini-1.5-flash",
                "gemini-2.5-flash"
            ]
            # Remove duplicates and empties while preserving order
            models_to_try = [m for i, m in enumerate(models_to_try) if m and m not in models_to_try[:i]]

            last_error = None
            for gemini_model in models_to_try:
                for attempt in range(3):
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
                        "model": gemini_model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens
                    }

                    try:
                        with httpx.Client(timeout=self.timeout) as client:
                            resp = client.post(openai_gemini_url, json=payload, headers=headers)
                            if resp.status_code == 200:
                                data = resp.json()
                                choices = data.get("choices", [])
                                if choices:
                                    raw_res = choices[0].get("message", {}).get("content", "").strip()
                                    from app.utils.thought_cleaner import strip_thought_content
                                    return strip_thought_content(raw_res)
                            elif resp.status_code == 429:
                                logger.warning(f"Gemini OpenAI endpoint rate limit (429) on attempt {attempt+1}. Retrying in 4s...")
                                time.sleep(4.0)
                                continue
                    except Exception:
                        pass

                    # Step B: Fallback to Native Gemini REST API (generateContent)
                    native_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={self.api_key}"
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
                        with httpx.Client(timeout=self.timeout) as client:
                            resp2 = client.post(native_endpoint, json=native_payload, headers=native_headers)
                            if resp2.status_code == 200:
                                data2 = resp2.json()
                                candidates = data2.get("candidates", [])
                                if candidates:
                                    parts = candidates[0].get("content", {}).get("parts", [])
                                    if parts:
                                        raw_res = parts[0].get("text", "").strip()
                                        from app.utils.thought_cleaner import strip_thought_content
                                        return strip_thought_content(raw_res)
                            elif resp2.status_code == 429:
                                logger.warning(f"Google Gemini rate limit (429) on attempt {attempt+1}. Retrying in 5s...")
                                time.sleep(5.0)
                                continue
                            else:
                                last_error = f"Google Gemini error {resp2.status_code}: {resp2.text[:300]}"
                                break
                    except Exception as e:
                        last_error = str(e)
                        logger.warning(f"Google Gemini request attempt {attempt+1} failed: {e}")
                        time.sleep(2.0)

            raise AIProviderError(f"Google Gemini request failed: {last_error or 'Rate limit or model error'}")

        # -------------------------------------------------------------
        # 3. OPENAI, OPENCODE, OPENROUTER, CUSTOM (Standard OpenAI format)
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
                "model": self.model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            # Only send thinking flags to OpenRouter / OpenCode
            if self.provider in ("opencode", "custom"):
                payload["chat_template_kwargs"] = {"enable_thinking": False}

            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                    if resp.status_code != 200:
                        raise AIProviderError(f"Online AI ({self.provider}) error {resp.status_code}: {resp.text}")
                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        return ""
                    raw_res = choices[0].get("message", {}).get("content", "").strip()
                    from app.utils.thought_cleaner import strip_thought_content
                    return strip_thought_content(raw_res)
            except Exception as e:
                logger.error(f"Online AI ({self.provider}) completion error: {e}")
                raise AIProviderError(f"Online AI request failed: {e}")

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
