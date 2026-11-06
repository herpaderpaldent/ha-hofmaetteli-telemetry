"""Sensor platform for hofmaetteli_telemetry: every mirrored entity that is not a binary sensor."""

from typing import TYPE_CHECKING

from custom_components.hofmaetteli_telemetry.const import CONF_ENTITIES

from .entity import HofmaetteliTelemetrySensor

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
    """Set up one sensor per selected remote entity outside the binary_sensor domain."""
    coordinator = entry.runtime_data.coordinator
    if coordinator is None:
        return
    async_add_entities(
        HofmaetteliTelemetrySensor(coordinator, remote_entity_id)
        for remote_entity_id in entry.options.get(CONF_ENTITIES, [])
        if not remote_entity_id.startswith("binary_sensor.")
    )
