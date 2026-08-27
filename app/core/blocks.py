"""Document AST Block definitions for SciDoc OCR."""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Tuple, Optional, Dict, Any
import uuid


class BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    FORMULA = "formula"
    TABLE = "table"
    FIGURE = "figure"
    CAPTION = "caption"
    LIST = "list"
    FOOTNOTE = "footnote"
    REFERENCE = "reference"
    CODE = "code"


@dataclass
class BoundingBox:
    """Bounding box coordinates (x0, y0, x1, y1) in PDF points or pixel units."""
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    def to_tuple(self) -> Tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)

    @classmethod
    def from_tuple(cls, coords: Tuple[float, float, float, float]) -> BoundingBox:
        if len(coords) == 4:
            return cls(x0=coords[0], y0=coords[1], x1=coords[2], y1=coords[3])
        return cls()


@dataclass
class BaseBlock:
    """Base class for all Document AST blocks."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    block_type: BlockType = BlockType.PARAGRAPH
    bbox: BoundingBox = field(default_factory=BoundingBox)
    confidence: float = 1.0  # 0.0 to 1.0
    source_page: int = 1     # 1-indexed
    order_index: int = 0
    column_index: int = 0    # 0 = left/single, 1 = right
    is_reviewed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["block_type"] = self.block_type.value
        data["bbox"] = self.bbox.to_tuple()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BaseBlock:
        return block_from_dict(data)


@dataclass
class HeadingBlock(BaseBlock):
    level: int = 1
    text: str = ""

    def __post_init__(self):
        self.block_type = BlockType.HEADING


@dataclass
class ParagraphBlock(BaseBlock):
    text: str = ""
    original_text: str = ""

    def __post_init__(self):
        self.block_type = BlockType.PARAGRAPH


@dataclass
class FormulaBlock(BaseBlock):
    latex: str = ""
    raw_text: str = ""
    is_inline: bool = False
    is_valid: bool = True
    issues: List[str] = field(default_factory=list)
    image_crop_path: Optional[str] = None

    def __post_init__(self):
        self.block_type = BlockType.FORMULA


@dataclass
class TableBlock(BaseBlock):
    rows: List[List[str]] = field(default_factory=list)
    header_rows: int = 1
    caption: str = ""
    raw_latex: str = ""

    def __post_init__(self):
        self.block_type = BlockType.TABLE


@dataclass
class FigureBlock(BaseBlock):
    image_path: str = ""
    caption: str = ""
    width_pt: float = 0.0
    height_pt: float = 0.0

    def __post_init__(self):
        self.block_type = BlockType.FIGURE


@dataclass
class CaptionBlock(BaseBlock):
    target_type: str = "figure"  # figure / table
    number: str = ""
    text: str = ""

    def __post_init__(self):
        self.block_type = BlockType.CAPTION


@dataclass
class ListBlock(BaseBlock):
    items: List[str] = field(default_factory=list)
    is_ordered: bool = False

    def __post_init__(self):
        self.block_type = BlockType.LIST


@dataclass
class FootnoteBlock(BaseBlock):
    mark: str = ""
    text: str = ""

    def __post_init__(self):
        self.block_type = BlockType.FOOTNOTE


@dataclass
class ReferenceBlock(BaseBlock):
    key: str = ""
    citation_text: str = ""

    def __post_init__(self):
        self.block_type = BlockType.REFERENCE


@dataclass
class CodeBlock(BaseBlock):
    language: str = ""
    code: str = ""

    def __post_init__(self):
        self.block_type = BlockType.CODE


def block_from_dict(data: Dict[str, Any]) -> BaseBlock:
    """Factory method to recreate any Block instance from a serialized dict."""
    data = dict(data)
    btype = data.get("block_type", "paragraph")
    if isinstance(btype, BlockType):
        btype_str = btype.value
    else:
        btype_str = str(btype)

    bbox_data = data.pop("bbox", (0.0, 0.0, 0.0, 0.0))
    if isinstance(bbox_data, (tuple, list)):
        bbox = BoundingBox.from_tuple(tuple(bbox_data))
    elif isinstance(bbox_data, dict):
        bbox = BoundingBox(**bbox_data)
    else:
        bbox = BoundingBox()

    data["bbox"] = bbox
    data["block_type"] = BlockType(btype_str)

    if btype_str == BlockType.HEADING.value:
        return HeadingBlock(**data)
    elif btype_str == BlockType.PARAGRAPH.value:
        return ParagraphBlock(**data)
    elif btype_str == BlockType.FORMULA.value:
        return FormulaBlock(**data)
    elif btype_str == BlockType.TABLE.value:
        return TableBlock(**data)
    elif btype_str == BlockType.FIGURE.value:
        return FigureBlock(**data)
    elif btype_str == BlockType.CAPTION.value:
        return CaptionBlock(**data)
    elif btype_str == BlockType.LIST.value:
        return ListBlock(**data)
    elif btype_str == BlockType.FOOTNOTE.value:
        return FootnoteBlock(**data)
    elif btype_str == BlockType.REFERENCE.value:
        return ReferenceBlock(**data)
    elif btype_str == BlockType.CODE.value:
        return CodeBlock(**data)
    else:
        return ParagraphBlock(**data)
