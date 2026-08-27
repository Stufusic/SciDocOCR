"""Document and Markdown Translator with Formula Protection."""

from typing import Optional, Callable
from app.core.document import Document
from app.core.blocks import BlockType, ParagraphBlock, HeadingBlock, TableBlock, CaptionBlock
from app.translation.parser import ProtectedBlockParser
from app.translation.validator import TranslationValidator
from app.ai.router import AIRouter
from app.core.exceptions import TranslationError
from app.utils.logging import get_logger

logger = get_logger("DocumentTranslator")

class DocumentTranslator:
    """Translates Document AST blocks while preserving formulas and code."""

    def __init__(self, ai_router: AIRouter):
        self.ai_router = ai_router
        self.parser = ProtectedBlockParser()
        self.validator = TranslationValidator()

    def translate_text_block(self, text: str, source_lang: str = "en", target_lang: str = "vi") -> str:
        """Translates a single paragraph or heading string safely."""
        if not text.strip():
            return text

        try:
            # 1. Mask math and code
            masked_text, placeholder_map = self.parser.mask_protected_elements(text)

            # 2. Call AI
            translated_masked = self.ai_router.translate_text(
                masked_text, source_lang=source_lang, target_lang=target_lang
            )

            # 3. Validate placeholders
            valid, missing = self.validator.validate_placeholders(translated_masked, placeholder_map)
            if not valid:
                logger.warning(f"Translation dropped {len(missing)} tokens: {missing}. Attempting recovery.")
                for token in missing:
                    translated_masked += f" {token}"

            # 4. Unmask
            final_text = self.parser.unmask_protected_elements(translated_masked, placeholder_map)
            return final_text
        except Exception as e:
            logger.warning(f"Translation failed for block ({e}). Preserving original text.")
            return text

    def translate_document(
        self,
        doc: Document,
        source_lang: str = "en",
        target_lang: str = "vi",
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Document:
        """Translates all text blocks in Document AST."""
        total_pages = len(doc.pages)
        for p_idx, page in enumerate(doc.pages):
            if progress_callback:
                progress_callback(p_idx + 1, total_pages, f"Translating page {p_idx + 1}/{total_pages}...")

            for block in page.blocks:
                if block.block_type == BlockType.PARAGRAPH and isinstance(block, ParagraphBlock):
                    block.text = self.translate_text_block(block.text, source_lang, target_lang)
                elif block.block_type == BlockType.HEADING and isinstance(block, HeadingBlock):
                    block.text = self.translate_text_block(block.text, source_lang, target_lang)
                elif block.block_type == BlockType.CAPTION and isinstance(block, CaptionBlock):
                    block.text = self.translate_text_block(block.text, source_lang, target_lang)
                elif block.block_type == BlockType.TABLE and isinstance(block, TableBlock):
                    new_rows = []
                    for row in block.rows:
                        new_row = [self.translate_text_block(cell, source_lang, target_lang) for cell in row]
                        new_rows.append(new_row)
                    block.rows = new_rows

            page.status = "translated"

        doc.metadata.target_language = target_lang
        return doc
