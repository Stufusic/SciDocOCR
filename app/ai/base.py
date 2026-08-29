"""AI Provider base interface."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from app.ai.prompts import (
    PROMPT_PROOFREAD_OCR,
    PROMPT_FORMULA_REPAIR,
    PROMPT_TRANSLATION,
    PROMPT_DOCUMENT_TO_MARKDOWN,
    PROMPT_VISION_OCR_PAGE,
    PROMPT_VISION_OCR_FORMULA,
    PROMPT_VISION_OCR_TABLE,
    PROMPT_VISION_OCR_SECTION
)

class AIProvider(ABC):
    """Abstract interface for LLM providers (LM Studio, OpenAI, Google Gemini, Anthropic Claude)."""

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the provider service is reachable."""
        pass

    @abstractmethod
    def generate(
        self,
        prompt: str = "",
        system_prompt: str = "",
        image_bytes: Optional[bytes] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096
    ) -> str:
        """Single unified core LLM call handling text, vision, system prompt, and model cascade."""
        pass

    def complete(self, prompt: str, system_prompt: str = "", temperature: float = 0.1, max_tokens: int = 2048) -> str:
        """Executes a text completion request."""
        return self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            image_bytes=None,
            temperature=temperature,
            max_tokens=max_tokens
        )

    def correct_text(self, text: str) -> str:
        """Corrects OCR errors in scientific text."""
        return self.generate(prompt=text, system_prompt=PROMPT_PROOFREAD_OCR, max_tokens=2048)

    def repair_formula(self, latex: str, issues: List[str]) -> str:
        """Repairs malformed LaTeX math expression."""
        issues_str = "\n".join(f"- {issue}" for issue in issues)
        prompt = f"Formula:\n```latex\n{latex}\n```\n\nDetected issues:\n{issues_str}"
        return self.generate(prompt=prompt, system_prompt=PROMPT_FORMULA_REPAIR, max_tokens=2048)

    def translate_text(self, text: str, source_lang: str = "en", target_lang: str = "vi") -> str:
        """Translates text while preserving special placeholder tokens."""
        sys_prompt = PROMPT_TRANSLATION.format(source_lang=source_lang, target_lang=target_lang)
        return self.generate(prompt=text, system_prompt=sys_prompt, max_tokens=4096)

    def document_to_markdown(self, page_content: str) -> str:
        """Reconstructs raw page content into clean, structured Markdown."""
        return self.generate(prompt=page_content, system_prompt=PROMPT_DOCUMENT_TO_MARKDOWN, max_tokens=4096)

    def ocr_image_to_markdown(self, image_bytes: bytes, raw_text_hint: str = "") -> str:
        """Transcribes document page image to Markdown using Vision AI."""
        if not image_bytes:
            return self.document_to_markdown(raw_text_hint)
        prompt = f"Raw text hint:\n{raw_text_hint}" if raw_text_hint else "Transcribe this page to Markdown with accurate LaTeX math and tables."
        return self.generate(
            prompt=prompt,
            system_prompt=PROMPT_VISION_OCR_PAGE,
            image_bytes=image_bytes,
            max_tokens=4096
        )

    def ocr_crop_to_markdown(self, crop_bytes: bytes, block_type: str = "text", hint: str = "") -> str:
        """Transcribes a specific cropped bounding box region (formula, table, section) to Markdown/LaTeX."""
        if not crop_bytes:
            return hint
        if block_type == "formula":
            sys_prompt = PROMPT_VISION_OCR_FORMULA
            prompt = "Transcribe this mathematical formula into clean LaTeX."
        elif block_type == "table":
            sys_prompt = PROMPT_VISION_OCR_TABLE
            prompt = "Transcribe this table into a clean Markdown table."
        else:
            sys_prompt = PROMPT_VISION_OCR_SECTION
            prompt = "Transcribe this document section into structured Markdown with inline LaTeX math."

        if hint:
            prompt += f"\nHint text: {hint}"

        return self.generate(
            prompt=prompt,
            system_prompt=sys_prompt,
            image_bytes=crop_bytes,
            max_tokens=2048
        )
