"""
API package for hofmaetteli_telemetry.

Exception hierarchy:
    HofmaetteliTelemetryApiClientError (base)
    ├── HofmaetteliTelemetryApiClientCommunicationError (network/timeout)
    │   └── HofmaetteliTelemetryApiClientRateLimitError (429, carries retry_after)
    └── HofmaetteliTelemetryApiClientAuthenticationError (401)
        └── HofmaetteliTelemetryApiClientForbiddenError (403, token lacks the role)

The coordinator, the publisher and the config flow validators map them onto Home Assistant
exceptions and form errors; entities never import this package.
"""

from .client import (
    HofmaetteliTelemetryApiClient,
    HofmaetteliTelemetryApiClientAuthenticationError,
    HofmaetteliTelemetryApiClientCommunicationError,
    HofmaetteliTelemetryApiClientError,
    HofmaetteliTelemetryApiClientForbiddenError,
    HofmaetteliTelemetryApiClientRateLimitError,
    RemoteEntity,
)

__all__ = [
    "HofmaetteliTelemetryApiClient",
    "HofmaetteliTelemetryApiClientAuthenticationError",
    "HofmaetteliTelemetryApiClientCommunicationError",
    "HofmaetteliTelemetryApiClientError",
    "HofmaetteliTelemetryApiClientForbiddenError",
    "HofmaetteliTelemetryApiClientRateLimitError",
    "RemoteEntity",
]
