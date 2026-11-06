"""Base entity class for hofmaetteli_telemetry."""

from typing import TYPE_CHECKING, Any

from yarl import URL

from custom_components.hofmaetteli_telemetry.const import ATTRIBUTION, MAPPED_ATTRIBUTES
from custom_components.hofmaetteli_telemetry.coordinator import HofmaetteliTelemetryDataUpdateCoordinator
from homeassistant.const import CONF_URL
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

if TYPE_CHECKING:
    from custom_components.hofmaetteli_telemetry.api import RemoteEntity

ATTR_REMOTE_ENTITY_ID = "remote_entity_id"
ATTR_REMOTE_LAST_UPDATED = "remote_last_updated"
ATTR_STALE = "stale"


class HofmaetteliTelemetryEntity(CoordinatorEntity[HofmaetteliTelemetryDataUpdateCoordinator]):
    """
    Base for an entity that mirrors one remote entity.

    The unique ID is `{entry_id}_{remote_entity_id}`. The server has no identity of its own,
    so the config entry ID is the stable anchor; the remote entity ID is unique per server.

    The device is named after the server's host, not the entry title, so the entity IDs derived
    from it stay the same whatever the entry is called.

    The name is the remote friendly name: it is supplied by the source, which is the
    documented exception to translated entity names.
    """

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HofmaetteliTelemetryDataUpdateCoordinator,
        remote_entity_id: str,
    ) -> None:
        """Initialize the entity from the remote entity it mirrors."""
        super().__init__(coordinator)
        self._remote_entity_id = remote_entity_id
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{remote_entity_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(entry.domain, entry.entry_id)},
            name=URL(entry.data[CONF_URL]).host or entry.data[CONF_URL],
            manufacturer="Hofmätteli Telemetry",
            model="Telemetry server",
            entry_type=DeviceEntryType.SERVICE,
        )
        remote = self.remote
        self._attr_name = remote.friendly_name if remote else remote_entity_id
        self._attr_icon = remote.attributes.get("icon") if remote else None

    @property
    def remote(self) -> RemoteEntity | None:
        """Return the latest data for the mirrored entity, or None if the server no longer has it."""
        return self.coordinator.data.get(self._remote_entity_id) if self.coordinator.data else None

    @property
    def available(self) -> bool:
        """Return True while the server answers and still knows the mirrored entity."""
        return super().available and self.remote is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the remote attributes that are not mapped to entity properties, plus freshness info."""
        remote = self.remote
        if remote is None:
            return {ATTR_REMOTE_ENTITY_ID: self._remote_entity_id}
        extra = {key: value for key, value in remote.attributes.items() if key not in MAPPED_ATTRIBUTES}
        return {
            **extra,
            ATTR_REMOTE_ENTITY_ID: self._remote_entity_id,
            ATTR_REMOTE_LAST_UPDATED: remote.ts,
            ATTR_STALE: remote.stale,
        }
