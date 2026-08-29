"""Markdown Parser: parses Markdown string into Document AST blocks."""

import re
from typing import List, Optional
from app.core.document import Document, PageData, DocumentMetadata
from app.core.blocks import (
    BaseBlock, HeadingBlock, ParagraphBlock, FormulaBlock,
    TableBlock, FigureBlock, CaptionBlock, CodeBlock, ListBlock,
    BoundingBox, BlockType
)

class MarkdownParser:
    """Parses GFM + Math Markdown back into Document AST."""

    def __init__(self):
        pass

    def parse_page_blocks(self, markdown_text: str, page_number: int = 1) -> List[BaseBlock]:
        """Parses a Markdown string representing a page into a list of BaseBlock instances."""
        blocks: List[BaseBlock] = []

        if not markdown_text or not markdown_text.strip():
            return blocks

        # Normalize boundaries so leading/trailing math and code blocks are caught reliably
        norm_text = f"\n{markdown_text.strip()}\n"

        # Split into blocks by double newlines or display math delimiters
        raw_chunks = re.split(r"(\n\$\$[\s\S]*?\$\$\n|\n```[\s\S]*?```\n|\n\n+)", norm_text)

        order_idx = 0
        for chunk in raw_chunks:
            chunk_str = chunk.strip()
            if not chunk_str:
                continue

            # 1. Display math: $$ ... $$
            if chunk_str.startswith("$$") and chunk_str.endswith("$$") and len(chunk_str) >= 4:
                math_body = chunk_str[2:-2].strip()
                blocks.append(FormulaBlock(
                    latex=math_body,
                    raw_text=chunk_str,
                    is_inline=False,
                    confidence=0.98,
                    source_page=page_number,
                    order_index=order_idx
                ))
                order_idx += 1

            # 2. Code block: ```lang ... ```
            elif chunk_str.startswith("```") and chunk_str.endswith("```") and len(chunk_str) >= 6:
                lines = chunk_str.split("\n")
                lang = lines[0][3:].strip()
                code_content = "\n".join(lines[1:-1])
                blocks.append(CodeBlock(
                    language=lang,
                    code=code_content,
                    confidence=0.99,
                    source_page=page_number,
                    order_index=order_idx
                ))
                order_idx += 1

            # 3. Figure image: ![caption](image_path)
            elif re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", chunk_str):
                m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", chunk_str)
                cap = m.group(1)
                img_path = m.group(2)
                blocks.append(FigureBlock(
                    caption=cap,
                    image_path=img_path,
                    confidence=0.99,
                    source_page=page_number,
                    order_index=order_idx
                ))
                order_idx += 1

            # 4. Heading: # ... or ## ...
            elif chunk_str.startswith("#"):
                match = re.match(r"^(#{1,6})\s+(.+)$", chunk_str)
                if match:
                    level = len(match.group(1))
                    text = match.group(2).strip()
                    blocks.append(HeadingBlock(
                        level=level,
                        text=text,
                        confidence=0.99,
                        source_page=page_number,
                        order_index=order_idx
                    ))
                    order_idx += 1
                else:
                    blocks.append(ParagraphBlock(
                        text=chunk_str,
                        confidence=0.95,
                        source_page=page_number,
                        order_index=order_idx
                    ))
                    order_idx += 1

            # 5. Caption: *Figure X: ...* or *Table X: ...*
            elif re.match(r"^\*(Figure|Fig\.|Table)\s+\d+[:\.].*\*$", chunk_str, re.IGNORECASE):
                clean_cap = chunk_str.strip("*").strip()
                target_type = "table" if "table" in clean_cap.lower() else "figure"
                blocks.append(CaptionBlock(
                    text=clean_cap,
                    target_type=target_type,
                    confidence=0.99,
                    source_page=page_number,
                    order_index=order_idx
                ))
                order_idx += 1

            # 6. Table: | col | col |
            elif "|" in chunk_str and ("\n|---" in chunk_str or "\n| ---" in chunk_str or chunk_str.startswith("|")):
                table_lines = [l.strip() for l in chunk_str.split("\n") if l.strip().startswith("|")]
                rows = []
                for l in table_lines:
                    if re.match(r"^\|(\s*:?-+:?\s*\|)+$", l):
                        continue  # Skip separator row
                    cells = [c.strip() for c in l.split("|")[1:-1]]
                    if any(cells):
                        rows.append(cells)
                if rows:
                    blocks.append(TableBlock(
                        rows=rows,
                        confidence=0.98,
                        source_page=page_number,
                        order_index=order_idx
                    ))
                    order_idx += 1
                else:
                    blocks.append(ParagraphBlock(
                        text=chunk_str,
                        confidence=0.95,
                        source_page=page_number,
                        order_index=order_idx
                    ))
                    order_idx += 1

            # 7. Ordered or Unordered List
            elif re.match(r"^(\d+\.|\-|\*)\s+", chunk_str):
                lines = chunk_str.split("\n")
                items = [re.sub(r"^(\d+\.|\-|\*)\s+", "", l).strip() for l in lines if l.strip()]
                is_ordered = bool(re.match(r"^\d+\.", lines[0].strip()))
                blocks.append(ListBlock(
                    items=items,
                    is_ordered=is_ordered,
                    confidence=0.98,
                    source_page=page_number,
                    order_index=order_idx
                ))
                order_idx += 1

            # 8. Regular Paragraph
            else:
                blocks.append(ParagraphBlock(
                    text=chunk_str,
                    confidence=0.95,
                    source_page=page_number,
                    order_index=order_idx
                ))
                order_idx += 1

        return blocks

    def parse_text(self, markdown_text: str) -> Document:
        doc = Document(metadata=DocumentMetadata(title="Parsed Markdown Document"))
        page_blocks = self.parse_page_blocks(markdown_text, page_number=1)
        page = PageData(page_number=1)
        for b in page_blocks:
            page.add_block(b)
        doc.add_page(page)
        return doc
