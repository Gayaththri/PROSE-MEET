"""Shared job lifecycle types for the processing pipeline."""


class JobCancelledError(RuntimeError):
    """Raised when the user cancels processing or when cooperative cancel checks fire."""
