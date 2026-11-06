"""
Diagnostics support for hofmaetteli_telemetry.

https://contributors.home-assistant.io/core/integrations/diagnostics/
"""

from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_API_TOKEN, CONF_URL
from homeassistant.helpers.redact import async_redact_data

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import HofmaetteliTelemetryConfigEntry

# The URL can identify the sharer's server, so it is redacted along with the token.
TO_REDACT = {
    CONF_API_TOKEN,
    CONF_URL,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: HofmaetteliTelemetryConfigEntry,
) -> dict[str, Any]:
    """
    Return diagnostics for a config entry.

    Returns:
        The redacted entry configuration and the current coordinator state.

    """
    coordinator = entry.runtime_data.coordinator
    publisher = entry.runtime_data.publisher

    diagnostics: dict[str, Any] = {
        "entry": {
            "version": entry.version,
            "minor_version": entry.minor_version,
            "state": str(entry.state),
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": async_redact_data(entry.options, TO_REDACT),
        },
    }
    if coordinator is not None:
        diagnostics["coordinator"] = {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
            "last_exception": str(coordinator.last_exception) if coordinator.last_exception else None,
            "remote_entities": sorted(coordinator.data or {}),
        }
    if publisher is not None:
        diagnostics["publisher"] = {
            "last_success": publisher.last_success.isoformat() if publisher.last_success else None,
            "last_error": publisher.last_error,
        }
    return diagnostics
