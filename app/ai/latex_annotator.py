"""LaTeX Annotator & Auditor: Fixes LaTeX OCR issues, inserts formula callout annotations, and translates text via LLM."""

from __future__ import annotations
import re
from typing import Optional
from app.utils.logging import get_logger
from app.ai.prompts import PROMPT_AUDIT_ANNOTATE_TRANSLATE

logger = get_logger("LatexAnnotator")

class LatexAnnotator:
    """Processes Markdown chunks through LLM to fix LaTeX syntax, add concept annotations, and translate text."""

    def __init__(self, ai_router = None):
        self.ai_router = ai_router

    def process_chunk_markdown(
        self,
        markdown_text: str,
        translate: bool = False,
        target_lang: str = "vi",
        timeout: float = 180.0
    ) -> str:
        """
        Runs Multi-Task LLM audit on markdown chunk:
        1. Fixes LaTeX math formulas
        2. Inserts `> 💡 **[Concept]** — [Explanation]` annotations below key equations
        3. Translates prose (if translate=True)
        """
        if not markdown_text or not markdown_text.strip():
            return markdown_text

        if self.ai_router is None:
            logger.info("AIRouter not configured; returning raw chunk Markdown.")
            return markdown_text

        try:
            provider = self.ai_router.get_active_provider()
            system_prompt = PROMPT_AUDIT_ANNOTATE_TRANSLATE.format(
                translate_flag=str(translate),
                target_lang="Vietnamese" if target_lang == "vi" else target_lang
            )

            prompt = (
                f"{system_prompt}\n\n"
                f"### SCIENTIFIC MARKDOWN CHUNK TO PROCESS:\n"
                f"{markdown_text}\n\n"
                f"### PROCESSED OUTPUT (Direct Markdown only):"
            )

            logger.info(f"Sending {len(markdown_text)} chars to {type(provider).__name__} for LaTeX Audit & Annotation...")
            raw_response = provider.complete(prompt, max_tokens=4096)

            if not raw_response or not raw_response.strip():
                logger.warning("Empty response from AI Provider; preserving raw markdown.")
                return markdown_text

            # Clean reasoning/thinking tokens (<think>...</think>)
            cleaned = re.sub(r"<think>.*?</think>", "", raw_response, flags=re.DOTALL).strip()

            # Clean markdown code block wrapper if present
            if cleaned.startswith("```markdown"):
                cleaned = cleaned[11:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]

            cleaned = cleaned.strip()

            if len(cleaned) > 20:
                logger.info(f"Successfully audited and annotated chunk ({len(cleaned)} chars).")
                return cleaned

            return markdown_text

        except Exception as e:
            logger.warning(f"LaTeX Audit & Annotation failed ({e}); preserving raw markdown.")
            return markdown_text
