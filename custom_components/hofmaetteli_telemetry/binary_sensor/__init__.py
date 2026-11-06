"""Binary sensor platform for hofmaetteli_telemetry: every mirrored entity in the binary_sensor domain."""

from typing import TYPE_CHECKING

from custom_components.hofmaetteli_telemetry.const import CONF_ENTITIES

from .entity import HofmaetteliTelemetryBinarySensor

# Read-only platform: the coordinator already serializes the fetch.
PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from custom_components.hofmaetteli_telemetry.data import HofmaetteliTelemetryConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HofmaetteliTelemetryConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one binary sensor per selected remote binary sensor."""
    coordinator = entry.runtime_data.coordinator
    if coordinator is None:
        return
    async_add_entities(
        HofmaetteliTelemetryBinarySensor(coordinator, remote_entity_id)
        for remote_entity_id in entry.options.get(CONF_ENTITIES, [])
        if remote_entity_id.startswith("binary_sensor.")
    )
