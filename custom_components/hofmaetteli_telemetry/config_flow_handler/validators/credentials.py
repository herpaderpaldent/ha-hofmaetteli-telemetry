"""Connection validation for the config flow."""

from typing import TYPE_CHECKING

from custom_components.hofmaetteli_telemetry.api import HofmaetteliTelemetryApiClient
from custom_components.hofmaetteli_telemetry.coordinator.publisher import is_publishable, json_safe_attributes
from homeassistant.helpers.aiohttp_client import async_get_clientsession

if TYPE_CHECKING:
    from custom_components.hofmaetteli_telemetry.api import RemoteEntity
    from homeassistant.core import HomeAssistant


async def validate_connection(
    hass: HomeAssistant,
    *,
    url: str,
    token: str,
    verify_ssl: bool,
) -> dict[str, RemoteEntity]:
    """
    Fetch the remote entities with the submitted URL and token.

    Args:
        hass: The Home Assistant instance.
        url: The base URL of the telemetry server.
        token: A token with the read or readwrite role.
        verify_ssl: Whether to verify the server's TLS certificate.

    Returns:
        The remote entities, so the next step can offer them without a second request.

    Raises:
        HofmaetteliTelemetryApiClientAuthenticationError: If the token is rejected.
        HofmaetteliTelemetryApiClientCommunicationError: If the server cannot be reached.
        HofmaetteliTelemetryApiClientError: For any other API failure.

    """
    client = HofmaetteliTelemetryApiClient(
        url=url,
        token=token,
        session=async_get_clientsession(hass, verify_ssl=verify_ssl),
    )
    return await client.async_get_entities()


async def validate_share_token(
    hass: HomeAssistant,
    *,
    url: str,
    token: str,
    verify_ssl: bool,
) -> None:
    """
    Check that the server answers and knows the token; a write-only token is fine here.

    Raises:
        HofmaetteliTelemetryApiClientAuthenticationError: If the server does not know the token.
        HofmaetteliTelemetryApiClientCommunicationError: If the server cannot be reached.
        HofmaetteliTelemetryApiClientError: For any other API failure.

    """
    client = HofmaetteliTelemetryApiClient(
        url=url,
        token=token,
        session=async_get_clientsession(hass, verify_ssl=verify_ssl),
    )
    await client.async_check_token()


async def push_current_states(
    hass: HomeAssistant,
    *,
    url: str,
    token: str,
    verify_ssl: bool,
    entity_ids: list[str],
) -> None:
    """
    Push the current state of the selected entities once.

    This is the only way to learn whether the token may write, and it puts data on the server
    right away instead of after the first change.

    Raises:
        HofmaetteliTelemetryApiClientForbiddenError: If the token lacks the write role.
        HofmaetteliTelemetryApiClientAuthenticationError: If the server does not know the token.
        HofmaetteliTelemetryApiClientCommunicationError: If the server cannot be reached.
        HofmaetteliTelemetryApiClientError: For any other API failure.

    """
    client = HofmaetteliTelemetryApiClient(
        url=url,
        token=token,
        session=async_get_clientsession(hass, verify_ssl=verify_ssl),
    )
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        if state is not None and is_publishable(state):
            await client.async_put_entity(state.entity_id, state.state, json_safe_attributes(state))


__all__ = ["push_current_states", "validate_connection", "validate_share_token"]
