"""Constants for hofmaetteli_telemetry."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "hofmaetteli_telemetry"
ATTRIBUTION = "Data provided by a Hofmätteli Telemetry server"

# Entry data key: whether this entry receives entities from the server or shares local ones to it.
CONF_MODE = "mode"
MODE_RECEIVE = "receive"
MODE_SHARE = "share"

# Options key: in receive mode the remote entity IDs to mirror, in share mode the local entity IDs to push.
CONF_ENTITIES = "entities"

# Remote attributes that become entity properties instead of extra state attributes.
MAPPED_ATTRIBUTES = frozenset(
    {
        "device_class",
        "friendly_name",
        "icon",
        "state_class",
        "unit_of_measurement",
    },
)
