"""Markdown Renderer: generates GFM + MathJax Markdown from Document AST."""

from app.core.document import Document
from app.core.blocks import (
    BaseBlock, BlockType, HeadingBlock, ParagraphBlock,
    FormulaBlock, TableBlock, FigureBlock, CaptionBlock,
    ListBlock, FootnoteBlock, ReferenceBlock, CodeBlock
)

class MarkdownRenderer:
    """Renders Document AST to clean Markdown."""

    def __init__(self):
        pass

    def render_block(self, block: BaseBlock) -> str:
        btype = block.block_type

        if btype == BlockType.HEADING and isinstance(block, HeadingBlock):
            prefix = "#" * max(1, min(6, block.level))
            return f"{prefix} {block.text}\n"

        elif btype == BlockType.PARAGRAPH and isinstance(block, ParagraphBlock):
            return f"{block.text}\n"

        elif btype == BlockType.FORMULA and isinstance(block, FormulaBlock):
            if block.is_inline:
                return f"${block.latex}$"
            return f"\n$$\n{block.latex}\n$$\n"

        elif btype == BlockType.TABLE and isinstance(block, TableBlock):
            if not block.rows:
                if getattr(block, "image_crop_path", None):
                    caption = block.caption or "Table"
                    return f"\n![{caption}]({block.image_crop_path})\n"
                return ""
            md_lines = []
            if block.caption:
                md_lines.append(f"**Table: {block.caption}**\n")

            # Header row
            header = block.rows[0]
            md_lines.append("| " + " | ".join(header) + " |")
            md_lines.append("| " + " | ".join(["---"] * len(header)) + " |")

            for row in block.rows[1:]:
                # Pad row to match header length
                padded = row + [""] * (len(header) - len(row))
                md_lines.append("| " + " | ".join(padded[:len(header)]) + " |")

            return "\n".join(md_lines) + "\n"

        elif btype == BlockType.FIGURE and isinstance(block, FigureBlock):
            caption = block.caption or "Figure"
            img = block.image_path or "image.png"
            return f"\n![{caption}]({img})\n"

        elif btype == BlockType.CAPTION and isinstance(block, CaptionBlock):
            text = (block.text or "").strip()
            return f"*{text}*\n\n"

        elif btype == BlockType.LIST and isinstance(block, ListBlock):
            lines = []
            for i, item in enumerate(block.items):
                prefix = f"{i+1}." if block.is_ordered else "-"
                lines.append(f"{prefix} {item}")
            return "\n".join(lines) + "\n"

        elif btype == BlockType.CODE and isinstance(block, CodeBlock):
            return f"```{block.language}\n{block.code}\n```\n"

        elif btype == BlockType.FOOTNOTE and isinstance(block, FootnoteBlock):
            return f"[^{block.mark}]: {block.text}\n"

        elif btype == BlockType.REFERENCE and isinstance(block, ReferenceBlock):
            return f"- [{block.key}] {block.citation_text}\n"

        return ""

    def render_document(self, doc: Document) -> str:
        """Renders the entire document to Markdown."""
        parts = []

        # Title / Header metadata
        if doc.metadata.title and doc.metadata.title != "Untitled Document":
            parts.append(f"# {doc.metadata.title}\n")
            if doc.metadata.author:
                parts.append(f"**Author:** {doc.metadata.author}\n")
            parts.append("---\n")

        for page in doc.pages:
            for block in page.blocks:
                rendered = self.render_block(block)
                if rendered:
                    parts.append(rendered)

        return "\n".join(parts)
