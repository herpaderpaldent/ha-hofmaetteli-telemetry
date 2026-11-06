"""
Share entities between Home Assistant installations through a Hofmätteli Telemetry server.

A config entry either receives (polls the server and mirrors entities) or shares (pushes
local entity states to the server); CONF_MODE in the entry data says which.

For more details about this integration, please refer to:
https://github.com/herpaderpaldent/ha-hofmaetteli-telemetry
"""

from typing import TYPE_CHECKING

from homeassistant.const import CONF_API_TOKEN, CONF_URL, CONF_VERIFY_SSL, Platform
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_loaded_integration

from .api import HofmaetteliTelemetryApiClient
from .const import CONF_ENTITIES, CONF_MODE, MODE_RECEIVE, MODE_SHARE
from .coordinator import HofmaetteliTelemetryDataUpdateCoordinator, HofmaetteliTelemetryPublisher
from .data import HofmaetteliTelemetryData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import HofmaetteliTelemetryConfigEntry

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HofmaetteliTelemetryConfigEntry,
) -> bool:
    """
    Set up a config entry.

    Returns:
        True once a share entry's publisher runs, or a receive entry's coordinator has data and every
        platform is forwarded.

    """
    client = HofmaetteliTelemetryApiClient(
        url=entry.data[CONF_URL],
        token=entry.data[CONF_API_TOKEN],
        session=async_get_clientsession(hass, verify_ssl=entry.data.get(CONF_VERIFY_SSL, True)),
    )
    integration = async_get_loaded_integration(hass, entry.domain)

    if entry.data.get(CONF_MODE, MODE_RECEIVE) == MODE_SHARE:
        publisher = HofmaetteliTelemetryPublisher(hass, entry, client, entry.options.get(CONF_ENTITIES, []))
        entry.runtime_data = HofmaetteliTelemetryData(client=client, integration=integration, publisher=publisher)
        publisher.async_start()
        return True

    coordinator = HofmaetteliTelemetryDataUpdateCoordinator(hass, entry)
    entry.runtime_data = HofmaetteliTelemetryData(client=client, integration=integration, coordinator=coordinator)

    await coordinator.async_config_entry_first_refresh()

    _async_remove_deselected_entities(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


def _async_remove_deselected_entities(hass: HomeAssistant, entry: HofmaetteliTelemetryConfigEntry) -> None:
    """
    Remove registry entries for remote entities the user deselected in the options.

    Without this, a deselected entity lingers as a restored, unavailable entity.
    """
    entity_registry = er.async_get(hass)
    selected = {f"{entry.entry_id}_{remote_entity_id}" for remote_entity_id in entry.options.get(CONF_ENTITIES, [])}
    for registry_entry in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if registry_entry.unique_id not in selected:
            entity_registry.async_remove(registry_entry.entity_id)


async def async_unload_entry(
    hass: HomeAssistant,
    entry: HofmaetteliTelemetryConfigEntry,
) -> bool:
    """
    Unload a config entry; the publisher's listeners and task go with the entry automatically.

    Returns:
        True if every platform unloaded cleanly.

    """
    if entry.data.get(CONF_MODE, MODE_RECEIVE) == MODE_SHARE:
        return True
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
