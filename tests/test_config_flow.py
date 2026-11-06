"""Tests for the config, options, reauth and reconfigure flows."""

from typing import Any
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hofmaetteli_telemetry import async_setup_entry
from custom_components.hofmaetteli_telemetry.const import CONF_ENTITIES, CONF_MODE, DOMAIN, MODE_RECEIVE
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_TOKEN, CONF_URL, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult, FlowResultType

SETUP_ENTRY = "custom_components.hofmaetteli_telemetry.async_setup_entry"
SERVER_URL = "https://telemetry.example.org"


async def start_flow(hass: HomeAssistant, mode: str) -> FlowResult:
    """
    Start the config flow and pick a mode in the menu.

    Returns:
        The connection form of that mode.

    """
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": mode})


async def test_receive_flow_creates_entry_with_selected_entities(
    hass: HomeAssistant,
    mock_server: AiohttpClientMocker,
    user_input: dict[str, Any],
) -> None:
    """URL and token lead to the entity picker, and the picked entities land in the options."""
    result = await start_flow(hass, MODE_RECEIVE)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "receive"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "receive_entities"

    with patch(SETUP_ENTRY, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ENTITIES: ["sensor.outdoor_temperature"]},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Receiving from telemetry.example.org"
    assert result["data"][CONF_URL] == SERVER_URL
    assert result["data"][CONF_MODE] == MODE_RECEIVE
    assert result["options"] == {CONF_ENTITIES: ["sensor.outdoor_temperature"]}
    assert mock_server.mock_calls[0][3] == {"Authorization": f"Bearer {user_input[CONF_API_TOKEN]}"}


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, "invalid_auth"),
        (403, "forbidden"),
        (500, "cannot_connect"),
    ],
)
async def test_receive_flow_reports_http_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    status: int,
    error: str,
    user_input: dict[str, Any],
    entities_url: str,
) -> None:
    """A rejected token and a server error show on the form instead of creating an entry."""
    aioclient_mock.get(entities_url, status=status)

    result = await start_flow(hass, MODE_RECEIVE)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_receive_flow_reports_unreachable_server(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    user_input: dict[str, Any],
    entities_url: str,
) -> None:
    """A server that does not answer shows cannot_connect."""
    aioclient_mock.get(entities_url, exc=TimeoutError)

    result = await start_flow(hass, MODE_RECEIVE)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)

    assert result["errors"] == {"base": "cannot_connect"}


async def test_receive_flow_aborts_when_server_shares_nothing(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    user_input: dict[str, Any],
    entities_url: str,
) -> None:
    """An empty server has nothing to pick, so the flow explains that instead of showing an empty list."""
    aioclient_mock.get(entities_url, json=[])

    result = await start_flow(hass, MODE_RECEIVE)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_entities"


async def test_receive_flow_refuses_the_same_server_twice(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    user_input: dict[str, Any],
) -> None:
    """The same URL, however it is typed, cannot be added a second time."""
    result = await start_flow(hass, MODE_RECEIVE)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_change_selection_and_reload_once(
    init_integration: MockConfigEntry,
    hass: HomeAssistant,
) -> None:
    """Deselecting an entity takes effect through one reload."""
    with patch(SETUP_ENTRY, wraps=async_setup_entry) as setup_entry:
        result = await hass.config_entries.options.async_init(init_integration.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_ENTITIES: ["binary_sensor.front_door"]},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options[CONF_ENTITIES] == ["binary_sensor.front_door"]
    assert setup_entry.call_count == 1
    assert hass.states.get("sensor.telemetry_example_org_outdoor_temperature") is None


async def test_reauth_replaces_the_token(
    init_integration: MockConfigEntry,
    hass: HomeAssistant,
) -> None:
    """A new token is stored and the entry reloads once."""
    with patch(SETUP_ENTRY, wraps=async_setup_entry) as setup_entry:
        result = await init_integration.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_API_TOKEN: "new-token"},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert init_integration.data[CONF_API_TOKEN] == "new-token"
    assert setup_entry.call_count == 1


async def test_reconfigure_updates_the_connection(
    init_integration: MockConfigEntry,
    hass: HomeAssistant,
) -> None:
    """Reconfigure stores the new connection details and reloads once."""
    with patch(SETUP_ENTRY, wraps=async_setup_entry) as setup_entry:
        result = await init_integration.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_URL: SERVER_URL, CONF_API_TOKEN: "other-token", CONF_VERIFY_SSL: False},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert init_integration.data[CONF_API_TOKEN] == "other-token"
    assert init_integration.data[CONF_VERIFY_SSL] is False
    assert setup_entry.call_count == 1
