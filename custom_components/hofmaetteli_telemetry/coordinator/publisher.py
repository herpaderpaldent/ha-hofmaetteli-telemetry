"""Publisher for hofmaetteli_telemetry: pushes local entity states to the server in share mode."""

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from custom_components.hofmaetteli_telemetry.api import (
    HofmaetteliTelemetryApiClientAuthenticationError,
    HofmaetteliTelemetryApiClientError,
    HofmaetteliTelemetryApiClientRateLimitError,
)
from custom_components.hofmaetteli_telemetry.const import LOGGER
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.json import json_dumps
from homeassistant.util import dt as dt_util
from homeassistant.util.json import json_loads_object

if TYPE_CHECKING:
    from custom_components.hofmaetteli_telemetry.api import HofmaetteliTelemetryApiClient
    from homeassistant.config_entries import ConfigEntry

# Re-push every selected entity this often, so the server does not mark a sensor that never changes as stale.
HEARTBEAT_INTERVAL = timedelta(hours=4)
MAX_RETRY_AFTER = 300.0

_UNPUBLISHABLE_STATES = frozenset({STATE_UNKNOWN, STATE_UNAVAILABLE})


def is_publishable(state: State | None) -> bool:
    """
    Tell whether a state is worth sending.

    Returns:
        False for a missing entity and for `unknown` / `unavailable`, which would overwrite the last good value.

    """
    return state is not None and state.state not in _UNPUBLISHABLE_STATES


def json_safe_attributes(state: State) -> dict[str, Any]:
    """
    Convert attributes to plain JSON types; they can hold datetimes, enums and other objects.

    Returns:
        The attributes as the server will store them.

    """
    return json_loads_object(json_dumps(dict(state.attributes)))


class HofmaetteliTelemetryPublisher:
    """
    Push the selected entities to the server: on every change, every HEARTBEAT_INTERVAL, and once at start.

    Pushes go through one drain task, one request at a time; it starts when something is queued
    and ends when the queue is empty. Changes that arrive while a push is running replace any
    older pending state of the same entity, so a chatty sensor costs one request per cycle and
    a burst stays within a reverse proxy's rate limit.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: HofmaetteliTelemetryApiClient,
        entity_ids: list[str],
    ) -> None:
        """Prepare the publisher; nothing is listened to or sent before async_start."""
        self._hass = hass
        self._entry = entry
        self._client = client
        self._entity_ids = entity_ids
        self._pending: dict[str, State] = {}
        self._drain_task: asyncio.Task[None] | None = None
        self._stopped = False
        self._failing = False
        self.last_success: datetime | None = None
        self.last_error: str | None = None

    @callback
    def async_start(self) -> None:
        """Queue every selected entity, then follow their changes and the heartbeat until the entry unloads."""
        self._entry.async_on_unload(
            async_track_state_change_event(self._hass, self._entity_ids, self._async_handle_state_change),
        )
        self._entry.async_on_unload(
            async_track_time_interval(self._hass, self._async_handle_heartbeat, HEARTBEAT_INTERVAL),
        )
        self._entry.async_on_unload(self._async_stop)
        self._async_queue_all()

    @callback
    def _async_stop(self) -> None:
        """Stop pushing; a drain task waiting out a rate limit would otherwise delay the unload."""
        self._stopped = True
        self._pending.clear()
        if self._drain_task is not None:
            self._drain_task.cancel()

    @callback
    def _async_handle_state_change(self, event: Event[EventStateChangedData]) -> None:
        """Queue a changed entity."""
        self._async_queue(event.data["new_state"])

    @callback
    def _async_handle_heartbeat(self, _now: datetime) -> None:
        """Queue every selected entity, changed or not."""
        self._async_queue_all()

    @callback
    def _async_queue_all(self) -> None:
        for entity_id in self._entity_ids:
            self._async_queue(self._hass.states.get(entity_id))

    @callback
    def _async_queue(self, state: State | None) -> None:
        if self._stopped or state is None or not is_publishable(state):
            return
        self._pending[state.entity_id] = state
        if self._drain_task is None or self._drain_task.done():
            self._drain_task = self._entry.async_create_task(
                self._hass,
                self._async_drain(),
                name=f"{self._entry.title} push",
            )

    async def _async_drain(self) -> None:
        """Send pending states one at a time until none are left."""
        while self._pending and not self._stopped:
            entity_id = next(iter(self._pending))
            state = self._pending.pop(entity_id)
            await self._async_send(state)

    async def _async_send(self, state: State) -> None:
        """Push one state, and handle the failure modes; a rejected token stops pushing until reauth reloads."""
        try:
            await self._client.async_put_entity(state.entity_id, state.state, json_safe_attributes(state))
        except HofmaetteliTelemetryApiClientAuthenticationError:
            LOGGER.error("The telemetry server rejected the token; stopping until it is replaced")
            self.last_error = "authentication_failed"
            self._async_stop()
            self._entry.async_start_reauth(self._hass)
            return
        except HofmaetteliTelemetryApiClientRateLimitError as exception:
            # Put it back unless a newer state arrived meanwhile, then wait as long as the server asked.
            self._pending.setdefault(state.entity_id, state)
            await asyncio.sleep(min(exception.retry_after, MAX_RETRY_AFTER))
            return
        except HofmaetteliTelemetryApiClientError as exception:
            # Dropped, not retried: the next change or heartbeat sends a fresh state anyway.
            self.last_error = str(exception)
            if not self._failing:
                LOGGER.warning("Could not push to the telemetry server, will retry on the next change: %s", exception)
                self._failing = True
            return

        if self._failing:
            LOGGER.info("Pushing to the telemetry server works again")
            self._failing = False
        self.last_success = dt_util.utcnow()
        self.last_error = None
