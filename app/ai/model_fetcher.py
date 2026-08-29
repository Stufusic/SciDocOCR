"""Model Fetcher: Full pre-populated model lists and dynamic API model discovery for OpenAI, Google Gemini, Anthropic Claude, and OpenCode/OpenRouter."""

from __future__ import annotations
import httpx
from typing import List, Dict, Optional
from app.utils.logging import get_logger

logger = get_logger("ModelFetcher")

# Full comprehensive lists of working models for each provider
FALLBACK_MODELS: Dict[str, List[str]] = {
    "openai": [
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4.5-preview",
        "o3-mini",
        "o1",
        "o1-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo"
    ],
    "google": [
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
        "gemini-1.5-pro",
        "gemini-1.0-pro"
    ],
    "anthropic": [
        "claude-3-7-sonnet-20250219",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
        "claude-3-haiku-20240307"
    ],
    "opencode": [
        "mineru2.5-pro-2605-1.2b",
        "qwen/qwen3.5-9b",
        "deepseek/deepseek-r1",
        "deepseek/deepseek-chat",
        "anthropic/claude-3.7-sonnet",
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o-mini",
        "openai/gpt-4o",
        "openai/o3-mini",
        "google/gemini-2.0-flash-001",
        "google/gemini-flash-1.5",
        "meta-llama/llama-3.3-70b-instruct",
        "qwen/qwen-2.5-72b-instruct",
        "mistralai/mistral-large-2411"
    ],
    "custom": [
        "mineru2.5-pro-2605-1.2b",
        "qwen/qwen3.5-9b",
        "gpt-4o-mini",
        "gpt-4o",
        "qwen2.5-72b",
        "llama-3.3-70b",
        "deepseek-r1"
    ]
}

DEFAULT_URLS: Dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
    "anthropic": "https://api.anthropic.com/v1",
    "opencode": "https://openrouter.ai/api/v1",
    "custom": "https://api.openai.com/v1"
}

def clean_google_model_name(raw_name: str) -> str:
    """Normalizes Google model names by removing 'models/' prefix."""
    return raw_name.replace("models/", "").strip()

def fetch_available_models(
    provider: str,
    api_key: str,
    base_url: Optional[str] = None,
    timeout: float = 6.0
) -> List[str]:
    """
    Connects to the provider's API with the given API key and returns
    a full list of available text/chat models.
    Combines live models from API with curated base models so the list is always complete.
    """
    prov = provider.lower()
    url = (base_url or DEFAULT_URLS.get(prov, "https://api.openai.com/v1")).rstrip("/")
    base_list = list(FALLBACK_MODELS.get(prov, FALLBACK_MODELS["openai"]))

    if not api_key:
        return base_list

    discovered_models: List[str] = []

    try:
        # 1. ANTHROPIC CLAUDE
        if prov == "anthropic":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            }
            with httpx.Client(timeout=timeout) as client:
                r = client.get(f"{url}/models", headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    discovered_models = [m.get("id") for m in data.get("data", []) if m.get("id")]

        # 2. GOOGLE GEMINI
        elif prov == "google":
            # Try Google native API list
            try:
                with httpx.Client(timeout=timeout) as client:
                    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                    r = client.get(gemini_url)
                    if r.status_code == 200:
                        data = r.json()
                        for m in data.get("models", []):
                            name = clean_google_model_name(m.get("name", ""))
                            # Filter text generation models
                            supported_methods = m.get("supportedGenerationMethods", [])
                            if "generateContent" in supported_methods or "gemini" in name.lower():
                                if not any(x in name for x in ["embedding", "bison", "aqa", "imagen"]):
                                    discovered_models.append(name)
            except Exception:
                pass

            # If native list was empty, try OpenAI-compatible endpoint
            if not discovered_models:
                try:
                    headers = {"Authorization": f"Bearer {api_key}"}
                    with httpx.Client(timeout=timeout) as client:
                        r = client.get(f"{url}/models", headers=headers)
                        if r.status_code == 200:
                            data = r.json()
                            for m in data.get("data", []):
                                mid = clean_google_model_name(m.get("id", ""))
                                if "gemini" in mid.lower():
                                    discovered_models.append(mid)
                except Exception:
                    pass

        # 3. OPENAI, OPENCODE / OPENROUTER, CUSTOM
        else:
            headers = {"Authorization": f"Bearer {api_key}"}
            with httpx.Client(timeout=timeout) as client:
                r = client.get(f"{url}/models", headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    raw_models = data.get("data", [])
                    ignore_keywords = {"embed", "whisper", "tts", "dall-e", "moderation", "davinci", "babbage", "curie", "audio"}
                    for m in raw_models:
                        mid = m.get("id", "")
                        if mid and not any(k in mid.lower() for k in ignore_keywords):
                            discovered_models.append(mid)

    except Exception as e:
        logger.warning(f"Failed to dynamically fetch models for provider '{provider}': {e}")

    # Merge discovered models with curated base models, keeping unique preserving order
    merged: List[str] = []
    seen = set()

    for m in discovered_models + base_list:
        if m and m not in seen:
            seen.add(m)
            merged.append(m)

    return merged if merged else base_list
