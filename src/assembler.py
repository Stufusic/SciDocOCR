"""Assembler: Replaces placeholders in draft skeleton with parsed LaTeX, tables, and chart summaries."""

from __future__ import annotations
import re
from pathlib import Path
from typing import Dict, Any, Optional

from config import OUTPUT_DIR
from src.vlm_client import refine_markdown
from app.utils.logging import get_logger

logger = get_logger("Assembler")

class DocumentAssembler:
    """Merges parsed multimodal components into the final clean Markdown document."""

    def __init__(self):
        pass

    def assemble(
        self,
        skeleton_content: str,
        replacements: Dict[str, str],
        refine_with_llm: bool = False,
        output_path: Optional[Path] = None
    ) -> str:
        """
        Substitutes all {{...}} placeholders with their corresponding parsed contents.
        """
        logger.info(f"Assembling document with {len(replacements)} replaced placeholders...")
        final_text = skeleton_content

        for placeholder, content in replacements.items():
            if placeholder in final_text:
                final_text = final_text.replace(placeholder, content)

        # Clean any unmatched leftover placeholders
        final_text = re.sub(r"\{\{[A-Z]+_PAGE_\d+_ID_\d+\}\}", "", final_text)

        # Normalize line spacing
        final_text = re.sub(r"\n{3,}", "\n\n", final_text).strip()

        # Optional LLM refinement
        if refine_with_llm:
            logger.info("Refining final document text with LLM text model...")
            final_text = refine_markdown(final_text)

        out_file = output_path or (OUTPUT_DIR / "final_output.md")
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(final_text, encoding="utf-8")
        logger.info(f"Final clean Markdown generated at: {out_file}")

        return final_text
