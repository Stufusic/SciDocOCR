"""AI Router: automatically routes between Online API and LM Studio with fallback."""

from typing import Optional, Dict, Any
from app.ai.base import AIProvider
from app.ai.lmstudio import LMStudioProvider
from app.ai.online import OnlineProvider
from app.network.connectivity import check_internet_connection
from app.core.exceptions import AIProviderError
from app.utils.logging import get_logger

logger = get_logger("AIRouter")

class AIRouter:
    """Intelligent router managing local and online AI providers with auto-fallback."""

    def __init__(
        self,
        mode: str = "auto",  # auto, local_only, online_only
        lmstudio_url: str = "http://127.0.0.1:1234/v1",
        lmstudio_model: str = "local-model",
        online_provider: str = "openai",
        online_key: str = "",
        online_url: str = "https://api.openai.com/v1",
        online_model: str = "gpt-4o-mini",
        translation_engine: str = "google_translate"
    ):
        self.mode = mode.lower()
        self.translation_engine = translation_engine
        self.lmstudio_provider = LMStudioProvider(base_url=lmstudio_url, model_name=lmstudio_model)
        self.online_provider = OnlineProvider(
            provider=online_provider,
            api_key=online_key,
            base_url=online_url,
            model_name=online_model
        )
        from app.translation.google_translate import GoogleTranslateService
        self.google_translate_service = GoogleTranslateService()

    def get_status(self) -> Dict[str, Any]:
        """Returns connection health of both engines."""
        internet_ok = check_internet_connection(timeout=1.5)
        online_ok = internet_ok and self.online_provider.is_available()
        lmstudio_ok = self.lmstudio_provider.is_available()

        active = "None"
        if self.mode == "local_only":
            active = "LM Studio" if lmstudio_ok else "Unavailable"
        elif self.mode == "online_only":
            active = f"Online ({self.online_provider.provider.capitalize()})" if online_ok else "Unavailable"
        else:  # auto
            if online_ok:
                active = f"Online ({self.online_provider.provider.capitalize()})"
            elif lmstudio_ok:
                active = "LM Studio (Offline)"
            else:
                active = "Unavailable"

        return {
            "internet": internet_ok,
            "online_ai": online_ok,
            "lmstudio": lmstudio_ok,
            "mode": self.mode,
            "active_provider": active,
            "translation_engine": self.translation_engine
        }

    def get_active_provider(self) -> AIProvider:
        """Determines and returns the best active AIProvider based on mode and connectivity."""
        if self.mode == "local_only":
            return self.lmstudio_provider

        if self.mode == "online_only":
            if self.online_provider.is_available():
                return self.online_provider
            raise AIProviderError(f"Online AI ({self.online_provider.provider}) is not available (check Internet or API key).")

        # AUTO mode: Try Online first, fallback to LM Studio
        if check_internet_connection(timeout=1.5) and self.online_provider.is_available():
            logger.info(f"AIRouter: Routing request to Online AI ({self.online_provider.provider}).")
            return self.online_provider

        if self.lmstudio_provider.is_available():
            logger.info("AIRouter: Falling back to local LM Studio provider.")
            return self.lmstudio_provider

        raise AIProviderError("No AI provider is available (neither Online API nor LM Studio).")

    def correct_text(self, text: str) -> str:
        provider = self.get_active_provider()
        return provider.correct_text(text)

    def translate_text(self, text: str, source_lang: str = "en", target_lang: str = "vi") -> str:
        # Fast & Free Google Translate engine
        if self.translation_engine == "google_translate":
            try:
                res = self.google_translate_service.translate_text(text, source_lang=source_lang, target_lang=target_lang)
                if res and res != text:
                    return res
            except Exception as e:
                logger.warning(f"Google Translate engine fallback: {e}")

        # Fallback or configured LLM AI Provider
        provider = self.get_active_provider()
        return provider.translate_text(text, source_lang=source_lang, target_lang=target_lang)

    def document_to_markdown(self, page_content: str) -> str:
        provider = self.get_active_provider()
        return provider.document_to_markdown(page_content)

    def ocr_image_to_markdown(self, image_bytes: bytes, raw_text_hint: str = "") -> str:
        provider = self.get_active_provider()
        return provider.ocr_image_to_markdown(image_bytes=image_bytes, raw_text_hint=raw_text_hint)
