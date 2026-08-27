"""PDF Page wrapper."""

from dataclasses import dataclass
from typing import Tuple, List, Dict, Any, Optional

@dataclass
class PDFPageInfo:
    page_number: int
    width: float
    height: float
    is_scanned: bool
    text_length: int
    image_count: int
    has_fonts: bool
    dpi: int = 150
