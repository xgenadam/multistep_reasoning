class DocumentError(Exception):
    """Base error for document operations."""


class DocumentApplyError(DocumentError):
    """Raised when a document operation cannot be applied."""


class DocumentIntegrityError(DocumentError):
    """Raised when a compose step would drop sub-task content."""
