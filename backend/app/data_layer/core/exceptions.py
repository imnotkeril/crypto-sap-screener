"""Custom exceptions for the data layer."""


class DataLayerError(Exception):
    """Base class for all data layer errors."""


class ValidationError(DataLayerError):
    """Raised when an incoming data point fails validation (dropped, not fatal)."""


class NormalizationError(DataLayerError):
    """Raised when a raw exchange message cannot be normalized."""


class StorageError(DataLayerError):
    """Raised on Redis/Postgres connectivity or query errors."""


class StartupError(DataLayerError):
    """Raised for unrecoverable errors during pipeline startup (should stop the process)."""
