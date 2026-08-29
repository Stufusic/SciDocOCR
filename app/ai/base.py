"""AI Provider base interface."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class AIProvider(ABC):
    """Abstract interface for LLM providers (LM Studio, OpenAI, Google Gemini, Anthropic Claude)."""

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the provider service is reachable."""
        pass

    @abstractmethod
    def complete(self, prompt: str, system_prompt: str = "", temperature: float = 0.2, max_tokens: int = 2048) -> str:
        """Executes a chat completion request and returns text response."""
        pass

    @abstractmethod
    def correct_text(self, text: str) -> str:
        """Corrects OCR errors in scientific text."""
        pass

    @abstractmethod
    def repair_formula(self, latex: str, issues: List[str]) -> str:
        """Repairs malformed LaTeX math expression."""
        pass

    @abstractmethod
    def translate_text(self, text: str, source_lang: str = "en", target_lang: str = "vi") -> str:
        """Translates text while preserving special placeholder tokens."""
        pass

    @abstractmethod
    def document_to_markdown(self, page_content: str) -> str:
        """Reconstructs raw page content into clean, structured Markdown with LaTeX math and tables."""
        pass

    def ocr_image_to_markdown(self, image_bytes: bytes, raw_text_hint: str = "") -> str:
        """Transcribes high-resolution document image to Markdown with LaTeX math and tables using Vision AI."""
        return self.document_to_markdown(raw_text_hint)
