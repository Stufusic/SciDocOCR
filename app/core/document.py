"""Document and Page representation for SciDoc OCR AST."""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Iterator
from app.core.blocks import BaseBlock, BlockType, block_from_dict


@dataclass
class PageData:
    """Represents a single page in the Document AST."""
    page_number: int  # 1-indexed
    width_pt: float = 595.0
    height_pt: float = 842.0
    is_scanned: bool = False
    text_density: float = 0.0
    sha256_hash: str = ""
    status: str = "pending"  # pending, ocr_done, validated, translated, error
    blocks: List[BaseBlock] = field(default_factory=list)
    preview_image_path: Optional[str] = None
    column_count: int = 1
    avg_confidence: float = 1.0

    def add_block(self, block: BaseBlock) -> None:
        block.source_page = self.page_number
        block.order_index = len(self.blocks)
        self.blocks.append(block)
        self.recompute_metrics()

    def remove_block(self, block_id: str) -> bool:
        initial_len = len(self.blocks)
        self.blocks = [b for b in self.blocks if b.id != block_id]
        if len(self.blocks) < initial_len:
            self.recompute_metrics()
            return True
        return False

    def recompute_metrics(self) -> None:
        if not self.blocks:
            self.avg_confidence = 1.0
            return
        total_conf = sum(b.confidence for b in self.blocks)
        self.avg_confidence = round(total_conf / len(self.blocks), 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "width_pt": self.width_pt,
            "height_pt": self.height_pt,
            "is_scanned": self.is_scanned,
            "text_density": self.text_density,
            "sha256_hash": self.sha256_hash,
            "status": self.status,
            "column_count": self.column_count,
            "avg_confidence": self.avg_confidence,
            "preview_image_path": self.preview_image_path,
            "blocks": [b.to_dict() for b in self.blocks],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PageData:
        data_copy = dict(data)
        blocks_data = data_copy.pop("blocks", [])
        page = cls(**data_copy)
        page.blocks = [block_from_dict(b) for b in blocks_data]
        return page


@dataclass
class DocumentMetadata:
    title: str = "Untitled Document"
    author: str = ""
    creation_date: str = ""
    source_pdf_path: str = ""
    file_hash: str = ""
    source_language: str = "en"
    target_language: str = "vi"
    page_count: int = 0


class Document:
    """Universal Document Representation (Document AST root)."""

    def __init__(self, metadata: Optional[DocumentMetadata] = None):
        self.metadata = metadata or DocumentMetadata()
        self.pages: List[PageData] = []

    def add_page(self, page: PageData) -> None:
        # Check if page already exists to prevent duplicate pages during resumption
        for idx, existing in enumerate(self.pages):
            if existing.page_number == page.page_number:
                self.pages[idx] = page
                return
        self.pages.append(page)
        self.pages.sort(key=lambda p: p.page_number)
        self.metadata.page_count = len(self.pages)

    def get_page(self, page_number: int) -> Optional[PageData]:
        for page in self.pages:
            if page.page_number == page_number:
                return page
        return None

    def get_all_blocks(self) -> Iterator[BaseBlock]:
        for page in self.pages:
            for block in page.blocks:
                yield block

    def get_blocks_by_type(self, btype: BlockType) -> List[BaseBlock]:
        return [b for b in self.get_all_blocks() if b.block_type == btype]

    def get_stats(self) -> Dict[str, Any]:
        total_blocks = 0
        formulas = 0
        tables = 0
        headings = 0
        total_conf = 0.0
        low_confidence_blocks = 0

        for block in self.get_all_blocks():
            total_blocks += 1
            total_conf += block.confidence
            if block.confidence < 0.85:
                low_confidence_blocks += 1
            if block.block_type == BlockType.FORMULA:
                formulas += 1
            elif block.block_type == BlockType.TABLE:
                tables += 1
            elif block.block_type == BlockType.HEADING:
                headings += 1

        avg_conf = (total_conf / total_blocks) if total_blocks > 0 else 1.0
        return {
            "page_count": len(self.pages),
            "total_blocks": total_blocks,
            "formula_count": formulas,
            "table_count": tables,
            "heading_count": headings,
            "avg_confidence": round(avg_conf, 4),
            "low_confidence_count": low_confidence_blocks,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": asdict(self.metadata),
            "pages": [p.to_dict() for p in self.pages],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Document:
        meta_dict = data.get("metadata", {})
        metadata = DocumentMetadata(**meta_dict)
        doc = cls(metadata=metadata)
        for page_dict in data.get("pages", []):
            doc.add_page(PageData.from_dict(page_dict))
        return doc
