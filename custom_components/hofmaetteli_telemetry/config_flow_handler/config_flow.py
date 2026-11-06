"""
Config flow for hofmaetteli_telemetry.

The first step is a menu: receive entities from the server, or share local entities to it.
Each path asks for the connection, then for the entities. Reconfigure and reauth follow
the mode stored in the entry.
"""

from typing import TYPE_CHECKING, Any

from yarl import URL

from custom_components.hofmaetteli_telemetry.api import (
    HofmaetteliTelemetryApiClientAuthenticationError,
    HofmaetteliTelemetryApiClientCommunicationError,
    HofmaetteliTelemetryApiClientForbiddenError,
)
from custom_components.hofmaetteli_telemetry.const import (
    CONF_ENTITIES,
    CONF_MODE,
    DOMAIN,
    LOGGER,
    MODE_RECEIVE,
    MODE_SHARE,
)
from homeassistant import config_entries
from homeassistant.const import CONF_API_TOKEN, CONF_URL, CONF_VERIFY_SSL

from .options_flow import HofmaetteliTelemetryOptionsFlow
from .schemas import get_connection_schema, get_entities_schema, get_local_entities_schema, get_token_schema
from .validators import push_current_states, validate_connection, validate_share_token

URL_PLACEHOLDERS = {"example_url": "https://telemetry.example.org"}

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from custom_components.hofmaetteli_telemetry.api import RemoteEntity


def _normalize_url(url: str) -> str:
    """
    Strip whitespace and trailing slashes so the same server is recognised however it was typed.

    Returns:
        The normalised URL.

    """
    return url.strip().rstrip("/")


async def _async_form_errors(call: Callable[[], Awaitable[Any]]) -> dict[str, str]:
    """
    Run a server call and turn its failure into form errors.

    Returns:
        An empty dict when the call worked, otherwise the errors for the form.

    """
    try:
        await call()
    except HofmaetteliTelemetryApiClientForbiddenError:
        return {"base": "forbidden"}
    except HofmaetteliTelemetryApiClientAuthenticationError:
        return {"base": "invalid_auth"}
    except HofmaetteliTelemetryApiClientCommunicationError:
        return {"base": "cannot_connect"}
    except Exception:  # noqa: BLE001 - Anything unexpected still has to reach the form.
        LOGGER.exception("Unexpected exception")
        return {"base": "unknown"}
    return {}


class HofmaetteliTelemetryConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """
    Handle the config flow for hofmaetteli_telemetry.

    The server exposes no identity of its own, so entries have no unique ID. A second entry
    for the same URL and mode is refused with `_async_abort_entries_match` instead; receiving
    from and sharing to the same server are separate entries.
    """

    VERSION = 1

    def __init__(self) -> None:
        """Keep the connection details and remote entities between the steps."""
        self._connection: dict[str, Any] = {}
        self._remote_entities: dict[str, RemoteEntity] = {}

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> HofmaetteliTelemetryOptionsFlow:
        """
        Return the options flow for this handler.

        Returns:
            The options flow instance.

        """
        return HofmaetteliTelemetryOptionsFlow()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Ask whether this Home Assistant receives or shares.

        Returns:
            The menu.

        """
        return self.async_show_menu(step_id="user", menu_options=[MODE_RECEIVE, MODE_SHARE])

    # Receive ---------------------------------------------------------------------------------

    async def async_step_receive(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Ask for the server URL and a read token, and check them by fetching the entities.

        Returns:
            The form, or the entity selection step.

        """
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input = self._prepare_connection(user_input, MODE_RECEIVE)
            errors = await self._async_validate(user_input)
            if not errors:
                self._connection = user_input
                return await self.async_step_receive_entities()

        return self.async_show_form(
            step_id="receive",
            data_schema=get_connection_schema(user_input),
            errors=errors,
            description_placeholders=URL_PLACEHOLDERS,
        )

    async def async_step_receive_entities(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Let the user pick which remote entities to mirror.

        Returns:
            The form, the abort when the server has nothing to share, or the created config entry.

        """
        if user_input is not None:
            return self.async_create_entry(
                title=f"Receiving from {self._host()}",
                data=self._connection,
                options={CONF_ENTITIES: user_input[CONF_ENTITIES]},
            )

        if not self._remote_entities:
            return self.async_abort(reason="no_entities")

        return self.async_show_form(
            step_id="receive_entities",
            data_schema=get_entities_schema(self._remote_entities.values()),
        )

    # Share -----------------------------------------------------------------------------------

    async def async_step_share(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Ask for the server URL and a write token, and check that the server knows the token.

        Returns:
            The form, or the entity selection step.

        """
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input = self._prepare_connection(user_input, MODE_SHARE)
            errors = await self._async_validate(user_input)
            if not errors:
                self._connection = user_input
                return await self.async_step_share_entities()

        return self.async_show_form(
            step_id="share",
            data_schema=get_connection_schema(user_input),
            errors=errors,
            description_placeholders=URL_PLACEHOLDERS,
        )

    async def async_step_share_entities(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Let the user pick local entities, then push them once to prove the token may write.

        Returns:
            The form, or the created config entry.

        """
        errors: dict[str, str] = {}

        if user_input is not None:
            connection = self._connection
            errors = await _async_form_errors(
                lambda: push_current_states(
                    self.hass,
                    url=connection[CONF_URL],
                    token=connection[CONF_API_TOKEN],
                    verify_ssl=connection.get(CONF_VERIFY_SSL, True),
                    entity_ids=user_input[CONF_ENTITIES],
                ),
            )
            if not errors:
                return self.async_create_entry(
                    title=f"Sharing to {self._host()}",
                    data=connection,
                    options={CONF_ENTITIES: user_input[CONF_ENTITIES]},
                )

        return self.async_show_form(
            step_id="share_entities",
            data_schema=get_local_entities_schema(user_input[CONF_ENTITIES] if user_input else ()),
            errors=errors,
        )

    # Reconfigure and reauth ------------------------------------------------------------------

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Change the URL, token or SSL setting of an existing entry.

        Returns:
            The form, or the abort that follows the entry update.

        """
        entry = self._get_reconfigure_entry()
        mode = entry.data.get(CONF_MODE, MODE_RECEIVE)
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input = {**user_input, CONF_URL: _normalize_url(user_input[CONF_URL])}
            if user_input[CONF_URL] != entry.data[CONF_URL]:
                self._async_abort_entries_match({CONF_URL: user_input[CONF_URL], CONF_MODE: mode})
            errors = await self._async_validate({**user_input, CONF_MODE: mode})
            if not errors:
                return self.async_update_reload_and_abort(entry, data_updates=user_input)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=get_connection_schema(user_input or entry.data),
            errors=errors,
            description_placeholders=URL_PLACEHOLDERS,
        )

    async def async_step_reauth(
        self,
        entry_data: dict[str, Any],
    ) -> config_entries.ConfigFlowResult:
        """
        Start reauthentication after the server rejected the token.

        Returns:
            The result of the reauth_confirm step.

        """
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Collect and verify a replacement token.

        Returns:
            The form, or the abort that follows the entry update.

        """
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await self._async_validate({**entry.data, **user_input})
            if not errors:
                return self.async_update_reload_and_abort(entry, data_updates=user_input)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=get_token_schema(),
            errors=errors,
            description_placeholders={"url": entry.data[CONF_URL]},
        )

    # Helpers ---------------------------------------------------------------------------------

    def _prepare_connection(self, user_input: dict[str, Any], mode: str) -> dict[str, Any]:
        """
        Normalise the URL, record the mode, and abort if this server is already set up in this mode.

        Returns:
            The connection details as they will be stored.

        """
        connection = {**user_input, CONF_URL: _normalize_url(user_input[CONF_URL]), CONF_MODE: mode}
        self._async_abort_entries_match({CONF_URL: connection[CONF_URL], CONF_MODE: mode})
        return connection

    def _host(self) -> str:
        """
        Return the server's host name, used as the entry title.

        Returns:
            The host, or the whole URL if it has none.

        """
        return URL(self._connection[CONF_URL]).host or self._connection[CONF_URL]

    async def _async_validate(self, connection: dict[str, Any]) -> dict[str, str]:
        """
        Check the connection the way its mode needs: receive fetches the entities, share checks the token.

        Returns:
            An empty dict when it works, otherwise the errors for the form.

        """
        url = connection[CONF_URL]
        token = connection[CONF_API_TOKEN]
        verify_ssl = connection.get(CONF_VERIFY_SSL, True)

        if connection.get(CONF_MODE, MODE_RECEIVE) == MODE_SHARE:
            return await _async_form_errors(
                lambda: validate_share_token(self.hass, url=url, token=token, verify_ssl=verify_ssl),
            )

        async def _fetch() -> None:
            self._remote_entities = await validate_connection(self.hass, url=url, token=token, verify_ssl=verify_ssl)

        return await _async_form_errors(_fetch)


__all__ = ["HofmaetteliTelemetryConfigFlowHandler"]
