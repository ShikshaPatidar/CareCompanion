class CareCompanionError(Exception):
    """Base class for errors this application raises on purpose."""


class ConfigError(CareCompanionError):
    """Missing or invalid configuration."""


class DataError(CareCompanionError):
    """Seed or state data could not be read or is malformed."""


class GatewayError(CareCompanionError):
    """A remote scheduling system failed in an unexpected way."""


class ExtractionError(CareCompanionError):
    """Document extraction produced output that failed validation."""
