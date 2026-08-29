import re
from typing import Optional, Callable, List
from app.core.document import Document, PageData
from app.core.blocks import BlockType, ParagraphBlock, HeadingBlock, TableBlock, CaptionBlock
from app.translation.parser import ProtectedBlockParser
from app.translation.validator import TranslationValidator
from app.ai.router import AIRouter
from app.storage.cache import CacheManager
from app.core.exceptions import TranslationError
from app.utils.logging import get_logger

logger = get_logger("DocumentTranslator")

class DocumentTranslator:
    """Translates Document AST blocks and raw Markdown sequentially in ~1500-character chunks while preserving formulas, code, and caching results."""

    def __init__(self, ai_router: AIRouter, cache_manager: Optional[CacheManager] = None):
        self.ai_router = ai_router
        self.cache_manager = cache_manager or CacheManager()
        self.parser = ProtectedBlockParser()
        self.validator = TranslationValidator()

    def translate_text_block(self, text: str, source_lang: str = "en", target_lang: str = "vi") -> str:
        """Translates a single paragraph or heading string safely with caching."""
        if not text or not text.strip():
            return text

        # Check Cache
        cached = self.cache_manager.get_cached_translation(text, target_lang)
        if cached:
            return cached

        try:
            # 1. Mask math and code
            masked_text, placeholder_map = self.parser.mask_protected_elements(text)

            # 2. Call AI / Translation Service
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

            # Store in cache
            self.cache_manager.store_cached_translation(text, target_lang, final_text)
            return final_text
        except Exception as e:
            logger.warning(f"Translation failed for block ({e}). Preserving original text.")
            return text

    def translate_page(
        self,
        page: PageData,
        source_lang: str = "en",
        target_lang: str = "vi",
        batch_size: int = 4
    ) -> PageData:
        """Translates all translatable blocks within a page in sequential batches of 4 blocks to avoid spawning excess tasks."""
        # Collect references to translatable blocks
        translatable_blocks = [
            b for b in page.blocks 
            if b.block_type in (BlockType.PARAGRAPH, BlockType.HEADING, BlockType.CAPTION, BlockType.TABLE)
        ]

        # Process sequentially in batches of 4 blocks
        for i in range(0, len(translatable_blocks), batch_size):
            batch = translatable_blocks[i:i + batch_size]
            for block in batch:
                if block.block_type == BlockType.PARAGRAPH and isinstance(block, ParagraphBlock):
                    block.text = self.translate_text_block(block.text, source_lang, target_lang)
                elif block.block_type == BlockType.HEADING and isinstance(block, HeadingBlock):
                    block.text = self.translate_text_block(block.text, source_lang, target_lang)
                elif block.block_type == BlockType.CAPTION and isinstance(block, CaptionBlock):
                    block.text = self.translate_text_block(block.text, source_lang, target_lang)
                elif block.block_type == BlockType.TABLE and isinstance(block, TableBlock):
                    if block.rows:
                        new_rows = []
                        for row in block.rows:
                            new_row = [self.translate_text_block(cell, source_lang, target_lang) for cell in row]
                            new_rows.append(new_row)
                        block.rows = new_rows

        page.status = "translated"
        return page

    def translate_document(
        self,
        doc: Document,
        source_lang: str = "en",
        target_lang: str = "vi",
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Document:
        """Translates all pages in Document AST sequentially (Page-by-Page)."""
        total_pages = len(doc.pages)
        for p_idx, page in enumerate(doc.pages):
            if progress_callback:
                progress_callback(p_idx + 1, total_pages, f"Đang dịch trang {p_idx + 1}/{total_pages}...")

            self.translate_page(page, source_lang, target_lang)

        doc.metadata.target_language = target_lang
        return doc

    def split_markdown_into_chunks(self, markdown_text: str, max_chars: int = 1500) -> List[str]:
        """
        Splits markdown text into coherent chunks of ~1500 characters,
        breaking at paragraph breaks (\n\n) or section headings without
        breaking math environments ($$...$$) or code blocks (```...```).
        """
        if not markdown_text or len(markdown_text) <= max_chars:
            return [markdown_text] if markdown_text else []

        # Split along double newlines (paragraphs)
        paragraphs = re.split(r"(\n\n+)", markdown_text)
        chunks = []
        current_chunk = []
        current_len = 0

        def has_unclosed_block(s: str) -> bool:
            code_ticks = len(re.findall(r"```", s))
            if code_ticks % 2 != 0:
                return True
            math_delims = len(re.findall(r"\$\$", s))
            if math_delims % 2 != 0:
                return True
            return False

        for part in paragraphs:
            part_len = len(part)
            candidate = "".join(current_chunk) + part

            if current_len + part_len <= max_chars or has_unclosed_block("".join(current_chunk)):
                current_chunk.append(part)
                current_len += part_len
            else:
                if current_chunk:
                    chunks.append("".join(current_chunk))
                    current_chunk = []
                    current_len = 0

                if part_len <= max_chars:
                    current_chunk.append(part)
                    current_len = part_len
                else:
                    lines = part.split("\n")
                    sub_buf = []
                    sub_len = 0
                    for line in lines:
                        if sub_len + len(line) + 1 <= max_chars or has_unclosed_block("".join(sub_buf)):
                            sub_buf.append(line)
                            sub_len += len(line) + 1
                        else:
                            if sub_buf:
                                chunks.append("\n".join(sub_buf))
                                sub_buf = []
                                sub_len = 0
                            sub_buf.append(line)
                            sub_len = len(line)
                    if sub_buf:
                        current_chunk.append("\n".join(sub_buf))
                        current_len = sum(len(x) for x in current_chunk)

        if current_chunk:
            chunks.append("".join(current_chunk))

        return [c for c in chunks if c.strip()] if chunks else [markdown_text]

    def translate_markdown_stream(
        self,
        markdown_text: str,
        source_lang: str = "en",
        target_lang: str = "vi",
        chunk_size: int = 1500,
        chunk_callback: Optional[Callable[[str, int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> str:
        """
        Translates markdown in chunks of ~1500 chars, preserving formulas, code, and images.
        Calls chunk_callback(accumulated_translated_text, chunk_idx, total_chunks) after each chunk.
        """
        chunks = self.split_markdown_into_chunks(markdown_text, max_chars=chunk_size)
        total_chunks = len(chunks)
        translated_pieces = []

        for idx, chunk in enumerate(chunks, 1):
            if cancel_check and cancel_check():
                break

            trans_chunk = self.translate_text_block(chunk, source_lang=source_lang, target_lang=target_lang)
            translated_pieces.append(trans_chunk)

            accumulated = "".join(translated_pieces)
            if chunk_callback:
                chunk_callback(accumulated, idx, total_chunks)

        return "".join(translated_pieces)
