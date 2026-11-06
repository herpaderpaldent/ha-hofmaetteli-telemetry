"""Binary sensor entity that mirrors a remote binary sensor for hofmaetteli_telemetry."""

from custom_components.hofmaetteli_telemetry.entity import HofmaetteliTelemetryEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.const import STATE_OFF, STATE_ON


class HofmaetteliTelemetryBinarySensor(BinarySensorEntity, HofmaetteliTelemetryEntity):
    """Binary sensor that takes its state and device class from the remote entity."""

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the remote device class, if it is one Home Assistant knows."""
        remote = self.remote
        value = remote.attributes.get("device_class") if remote else None
        try:
            return BinarySensorDeviceClass(value) if value is not None else None
        except ValueError:
            return None

    @property
    def is_on(self) -> bool | None:
        """Return the remote state; anything other than on or off is unknown."""
        remote = self.remote
        if remote is None:
            return None
        if remote.state == STATE_ON:
            return True
        if remote.state == STATE_OFF:
            return False
        return None
