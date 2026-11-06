"""API client for the Hofmätteli Telemetry server."""

import asyncio
from dataclasses import dataclass
from http import HTTPStatus
import math
import socket
from typing import Any

import aiohttp
from aiohttp import hdrs

REQUEST_TIMEOUT = 10
DEFAULT_RETRY_AFTER = 60


class HofmaetteliTelemetryApiClientError(Exception):
    """Base exception to indicate a general API error."""


class HofmaetteliTelemetryApiClientCommunicationError(
    HofmaetteliTelemetryApiClientError,
):
    """Exception to indicate a communication error with the API."""


class HofmaetteliTelemetryApiClientAuthenticationError(
    HofmaetteliTelemetryApiClientError,
):
    """Exception to indicate the token was rejected (401) or lacks the needed role (403)."""


class HofmaetteliTelemetryApiClientForbiddenError(
    HofmaetteliTelemetryApiClientAuthenticationError,
):
    """Exception to indicate the token is valid but lacks the role for this request (403)."""


class HofmaetteliTelemetryApiClientRateLimitError(
    HofmaetteliTelemetryApiClientCommunicationError,
):
    """Exception to indicate the API (or a proxy in front of it) asked for fewer requests."""

    def __init__(self, message: str, retry_after: float) -> None:
        """Keep the seconds the API asked to wait before the next request."""
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True, slots=True)
class RemoteEntity:
    """One entity as the telemetry server reports it."""

    entity_id: str
    state: str
    attributes: dict[str, Any]
    ts: str
    stale: bool

    @property
    def domain(self) -> str:
        """Return the Home Assistant domain of the remote entity, such as `sensor`."""
        return self.entity_id.split(".", 1)[0]

    @property
    def friendly_name(self) -> str:
        """Return the remote friendly name, falling back to the entity ID."""
        return str(self.attributes.get("friendly_name") or self.entity_id)


def _retry_after(response: aiohttp.ClientResponse) -> float:
    """
    Read the wait the API asked for.

    Returns:
        The Retry-After header in seconds, or DEFAULT_RETRY_AFTER when it is missing or not a number of seconds.

    """
    try:
        seconds = float(response.headers.get(hdrs.RETRY_AFTER, ""))
    except ValueError:
        return DEFAULT_RETRY_AFTER
    return seconds if math.isfinite(seconds) and seconds >= 0 else DEFAULT_RETRY_AFTER


def _verify_response_or_raise(response: aiohttp.ClientResponse) -> None:
    """
    Verify that the API response is valid.

    Raises:
        HofmaetteliTelemetryApiClientForbiddenError: For 403 responses.
        HofmaetteliTelemetryApiClientAuthenticationError: For 401 responses.
        HofmaetteliTelemetryApiClientRateLimitError: For 429 responses.
        aiohttp.ClientResponseError: For every other unsuccessful status.

    """
    if response.status == HTTPStatus.FORBIDDEN:
        msg = "Token lacks the role for this request"
        raise HofmaetteliTelemetryApiClientForbiddenError(msg)
    if response.status == HTTPStatus.UNAUTHORIZED:
        msg = "Token rejected"
        raise HofmaetteliTelemetryApiClientAuthenticationError(msg)
    if response.status == HTTPStatus.TOO_MANY_REQUESTS:
        msg = "Rate limited by the API"
        raise HofmaetteliTelemetryApiClientRateLimitError(msg, retry_after=_retry_after(response))
    response.raise_for_status()


def _parse_entity(item: Any) -> RemoteEntity:
    """
    Turn one item of the `GET /entities?full=true` response into a RemoteEntity.

    Returns:
        The parsed entity.

    Raises:
        HofmaetteliTelemetryApiClientError: If the item does not have the expected shape.

    """
    try:
        attributes = item.get("attributes") or {}
        if not isinstance(attributes, dict):
            attributes = {}
        return RemoteEntity(
            entity_id=str(item["entity_id"]),
            state=str(item["state"]),
            attributes=attributes,
            ts=str(item["ts"]),
            stale=bool(item.get("stale", False)),
        )
    except (AttributeError, KeyError, TypeError) as exception:
        msg = f"Unexpected entity in API response: {item!r}"
        raise HofmaetteliTelemetryApiClientError(msg) from exception


class HofmaetteliTelemetryApiClient:
    """Client for the telemetry server's `/entities` endpoints."""

    def __init__(
        self,
        url: str,
        token: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize the API client; SSL verification is a property of the session."""
        self._base_url = url.rstrip("/")
        self._token = token
        self._session = session

    async def async_get_entities(self) -> dict[str, RemoteEntity]:
        """
        Fetch every entity the server knows, with full data, in one request.

        Returns:
            The remote entities keyed by their entity ID.

        Raises:
            HofmaetteliTelemetryApiClientError: If the response is not a list of entities.

        """
        response = await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/entities",
            params={"full": "true"},
        )
        if not isinstance(response, list):
            msg = f"Expected a list of entities, got {type(response).__name__}"
            raise HofmaetteliTelemetryApiClientError(msg)
        entities = (_parse_entity(item) for item in response)
        return {entity.entity_id: entity for entity in entities}

    async def async_check_token(self) -> None:
        """
        Check that the server answers and knows the token, whatever its role.

        A write-only token gets 403 on the read endpoint, which still proves the token exists;
        only 401 means it is unknown. Whether it may write shows on the first PUT.

        Raises:
            HofmaetteliTelemetryApiClientAuthenticationError: If the server does not know the token.
            HofmaetteliTelemetryApiClientCommunicationError: If the server cannot be reached.

        """
        try:
            await self._api_wrapper(method="get", url=f"{self._base_url}/entities")
        except HofmaetteliTelemetryApiClientForbiddenError:
            return

    async def async_put_entity(self, entity_id: str, state: str, attributes: dict[str, Any]) -> None:
        """
        Store the current state of one entity on the server.

        No `last_changed` is sent, so the server records the time it received the value. That is what
        its `stale` flag needs: a periodic push of an unchanged sensor counts as fresh.
        """
        await self._api_wrapper(
            method="put",
            url=f"{self._base_url}/entities/{entity_id}",
            json={"state": state, "attributes": attributes},
        )

    async def _api_wrapper(
        self,
        method: str,
        url: str,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """
        Perform a request and translate transport errors into client exceptions.

        Returns:
            The decoded JSON response, or None for 204 No Content.

        Raises:
            HofmaetteliTelemetryApiClientAuthenticationError: If the token is rejected or lacks the role.
            HofmaetteliTelemetryApiClientRateLimitError: If the API asks for fewer requests.
            HofmaetteliTelemetryApiClientCommunicationError: If the request does not complete.
            HofmaetteliTelemetryApiClientError: For any other failure.

        """
        try:
            async with (
                asyncio.timeout(REQUEST_TIMEOUT),
                self._session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                    headers={hdrs.AUTHORIZATION: f"Bearer {self._token}"},
                ) as response,
            ):
                _verify_response_or_raise(response)
                if response.status == HTTPStatus.NO_CONTENT:
                    return None
                return await response.json()

        except TimeoutError as exception:
            msg = f"Timeout error fetching information - {exception}"
            raise HofmaetteliTelemetryApiClientCommunicationError(msg) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"Error fetching information - {exception}"
            raise HofmaetteliTelemetryApiClientCommunicationError(msg) from exception
        except HofmaetteliTelemetryApiClientError:
            raise
        except Exception as exception:
            msg = f"Unexpected error talking to the API - {exception}"
            raise HofmaetteliTelemetryApiClientError(msg) from exception
