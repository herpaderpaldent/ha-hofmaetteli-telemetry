"""
Entity package for hofmaetteli_telemetry.

Architecture:
    All platform entities inherit from (PlatformEntity, HofmaetteliTelemetryEntity).
    MRO order matters — platform-specific class first, then the integration base.
    Entities read data from coordinator.data and NEVER call the API client directly.
    Unique IDs follow the pattern: {entry_id}_{description.key}

See entity/base.py for the HofmaetteliTelemetryEntity base class.
"""

from .base import HofmaetteliTelemetryEntity

__all__ = ["HofmaetteliTelemetryEntity"]
