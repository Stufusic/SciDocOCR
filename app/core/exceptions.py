"""Custom exceptions for SciDoc OCR application."""

class SciDocException(Exception):
    """Base exception for all SciDoc OCR errors."""
    pass

class PDFProcessingError(SciDocException):
    """Raised when PDF reading or processing fails."""
    pass

class OCRError(SciDocException):
    """Raised when OCR extraction fails."""
    pass

class FormulaParsingError(SciDocException):
    """Raised when formula parsing or validation fails."""
    pass

class AIProviderError(SciDocException):
    """Raised when AI provider connection or completion fails."""
    pass

class TranslationError(SciDocException):
    """Raised when translation fails or formula verification fails."""
    pass

class LaTeXCompilationError(SciDocException):
    """Raised when LaTeX generation or compilation fails."""
    def __init__(self, message: str, log_output: str = "", error_line: int = -1):
        super().__init__(message)
        self.log_output = log_output
        self.error_line = error_line

class ProjectError(SciDocException):
    """Raised when project loading, saving or integrity check fails."""
    pass
