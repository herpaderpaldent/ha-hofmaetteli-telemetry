"""Sensor entity that mirrors a remote sensor for hofmaetteli_telemetry."""

from datetime import date, datetime
from decimal import Decimal

from custom_components.hofmaetteli_telemetry.entity import HofmaetteliTelemetryEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.util import dt as dt_util

# Device classes whose state is text, not a number.
_NON_NUMERIC_DEVICE_CLASSES = frozenset({SensorDeviceClass.ENUM, SensorDeviceClass.DATE, SensorDeviceClass.TIMESTAMP})


def _parse_enum[T: (SensorDeviceClass, SensorStateClass)](enum: type[T], value: object) -> T | None:
    """
    Read a remote attribute as a member of a Home Assistant enum.

    Returns:
        The enum member, or None when the attribute is missing or not a known value.

    """
    try:
        return enum(value) if value is not None else None
    except ValueError:
        return None


class HofmaetteliTelemetrySensor(SensorEntity, HofmaetteliTelemetryEntity):
    """Sensor that takes its state, unit and classes from the remote entity."""

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return the remote device class, if it is one Home Assistant knows."""
        remote = self.remote
        return _parse_enum(SensorDeviceClass, remote.attributes.get("device_class")) if remote else None

    @property
    def state_class(self) -> SensorStateClass | None:
        """Return the remote state class, if it is one Home Assistant knows."""
        remote = self.remote
        return _parse_enum(SensorStateClass, remote.attributes.get("state_class")) if remote else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the remote unit of measurement."""
        remote = self.remote
        unit = remote.attributes.get("unit_of_measurement") if remote else None
        return str(unit) if unit is not None else None

    @property
    def native_value(self) -> str | int | float | date | datetime | Decimal | None:
        """
        Return the remote state, converted to the type its device class expects.

        A numeric sensor whose remote state is not a number, such as `unknown`, reports None,
        because Home Assistant rejects text in a sensor that has a unit or a numeric device class.
        """
        remote = self.remote
        if remote is None or remote.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None

        device_class = self.device_class
        if device_class is SensorDeviceClass.TIMESTAMP:
            return dt_util.parse_datetime(remote.state)
        if device_class is SensorDeviceClass.DATE:
            return dt_util.parse_date(remote.state)
        if device_class in _NON_NUMERIC_DEVICE_CLASSES:
            return remote.state

        if device_class is None and self.native_unit_of_measurement is None and self.state_class is None:
            return remote.state

        try:
            return float(remote.state)
        except ValueError:
            return None
