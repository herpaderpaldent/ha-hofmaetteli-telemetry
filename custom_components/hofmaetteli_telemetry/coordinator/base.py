"""Data update coordinator for hofmaetteli_telemetry."""

from datetime import timedelta
from typing import TYPE_CHECKING

from custom_components.hofmaetteli_telemetry.api import (
    HofmaetteliTelemetryApiClientAuthenticationError,
    HofmaetteliTelemetryApiClientError,
    HofmaetteliTelemetryApiClientRateLimitError,
    RemoteEntity,
)
from custom_components.hofmaetteli_telemetry.const import DOMAIN, LOGGER
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

if TYPE_CHECKING:
    from custom_components.hofmaetteli_telemetry.data import HofmaetteliTelemetryConfigEntry
    from homeassistant.core import HomeAssistant

MIN_RETRY_AFTER = 10.0
UPDATE_INTERVAL = timedelta(seconds=60)


class HofmaetteliTelemetryDataUpdateCoordinator(DataUpdateCoordinator[dict[str, RemoteEntity]]):
    """Fetch every remote entity in one request per interval and hand them to the entities."""

    config_entry: HofmaetteliTelemetryConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: HofmaetteliTelemetryConfigEntry) -> None:
        """Set up the coordinator for one config entry."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=UPDATE_INTERVAL,
            always_update=False,
        )

    async def _async_update_data(self) -> dict[str, RemoteEntity]:
        """
        Fetch the remote entities.

        Returns:
            The remote entities keyed by their entity ID.

        Raises:
            ConfigEntryAuthFailed: If the token was rejected; triggers reauth.
            UpdateFailed: If the fetch failed for any other reason; after a rate limit, it carries the wait the API
                asked for.

        """
        try:
            return await self.config_entry.runtime_data.client.async_get_entities()
        except HofmaetteliTelemetryApiClientAuthenticationError as exception:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="authentication_failed",
            ) from exception
        except HofmaetteliTelemetryApiClientRateLimitError as exception:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                retry_after=self._bounded_retry_after(exception.retry_after),
            ) from exception
        except HofmaetteliTelemetryApiClientError as exception:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
            ) from exception

    def _bounded_retry_after(self, seconds: float) -> float:
        """
        Keep the wait a rate limit asks for between MIN_RETRY_AFTER and ten regular update intervals.

        Returns:
            The seconds until the next poll.

        """
        if self.update_interval:
            seconds = min(seconds, 10 * self.update_interval.total_seconds())
        return max(seconds, MIN_RETRY_AFTER)
