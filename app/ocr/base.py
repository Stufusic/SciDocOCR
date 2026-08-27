"""Base OCR class interface for SciDoc OCR."""

from abc import ABC, abstractmethod
from typing import List, Optional
from app.core.blocks import BaseBlock

class BaseOCR(ABC):
    """Abstract interface for all OCR engines (Local, Online, Formula)."""

    @abstractmethod
    def process_page_blocks(self, blocks: List[BaseBlock], page_index: int, image_bytes: Optional[bytes] = None) -> List[BaseBlock]:
        """Processes extracted blocks, identifies formulas/tables, and refines OCR text."""
        pass
