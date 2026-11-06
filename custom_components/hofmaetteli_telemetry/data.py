"""
Runtime data types for hofmaetteli_telemetry.

Access pattern: entry.runtime_data.client / entry.runtime_data.coordinator
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import HofmaetteliTelemetryApiClient
    from .coordinator import HofmaetteliTelemetryDataUpdateCoordinator, HofmaetteliTelemetryPublisher


type HofmaetteliTelemetryConfigEntry = ConfigEntry[HofmaetteliTelemetryData]


@dataclass
class HofmaetteliTelemetryData:
    """
    Runtime data stored on the config entry after a successful setup.

    A receive entry has a coordinator and no publisher; a share entry the other way round.
    """

    client: HofmaetteliTelemetryApiClient
    integration: Integration
    coordinator: HofmaetteliTelemetryDataUpdateCoordinator | None = None
    publisher: HofmaetteliTelemetryPublisher | None = None
