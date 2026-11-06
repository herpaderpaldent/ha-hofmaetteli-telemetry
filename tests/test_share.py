"""Tests for share mode: the config flow path and the publisher that pushes local states."""

from datetime import timedelta
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hofmaetteli_telemetry.const import CONF_ENTITIES, CONF_MODE, DOMAIN, MODE_SHARE
from custom_components.hofmaetteli_telemetry.coordinator.publisher import HEARTBEAT_INTERVAL
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult, FlowResultType
from homeassistant.util import dt as dt_util

SETUP_ENTRY = "custom_components.hofmaetteli_telemetry.async_setup_entry"


def puts(mocker: AiohttpClientMocker) -> dict[str, Any]:
    """
    Collect the pushes the mocker saw.

    Returns:
        The last pushed JSON body per URL path.

    """
    return {str(call[1].path): call[2] for call in mocker.mock_calls if call[0].lower() == "put"}


def put_count(mocker: AiohttpClientMocker) -> int:
    """
    Count the pushes the mocker saw.

    Returns:
        The number of PUT requests.

    """
    return sum(1 for call in mocker.mock_calls if call[0].lower() == "put")


async def start_share_flow(hass: HomeAssistant) -> FlowResult:
    """
    Start the config flow and pick share in the menu.

    Returns:
        The share connection form.

    """
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": MODE_SHARE})


# Config flow -----------------------------------------------------------------------------------


@pytest.mark.usefixtures("local_states")
async def test_share_flow_pushes_selection_and_creates_entry(
    hass: HomeAssistant,
    mock_put: AiohttpClientMocker,
    user_input: dict[str, Any],
) -> None:
    """A write-only token passes the check, and the selection is pushed once before the entry exists."""
    result = await start_share_flow(hass)
    assert result["step_id"] == "share"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    assert result["step_id"] == "share_entities"

    with patch(SETUP_ENTRY, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ENTITIES: ["sensor.living_room_temperature", "binary_sensor.window"]},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Sharing to telemetry.example.org"
    assert result["data"][CONF_MODE] == MODE_SHARE
    assert result["options"] == {CONF_ENTITIES: ["sensor.living_room_temperature", "binary_sensor.window"]}
    pushed = puts(mock_put)
    assert pushed["/entities/sensor.living_room_temperature"]["state"] == "21.5"
    assert pushed["/entities/binary_sensor.window"]["state"] == "off"


@pytest.mark.usefixtures("local_states")
async def test_share_flow_rejects_read_only_token(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entities_url: str,
    user_input: dict[str, Any],
) -> None:
    """A read token passes the check but cannot write, so the selection step says so."""
    aioclient_mock.get(entities_url, json=[])
    aioclient_mock.put(f"{entities_url}/sensor.living_room_temperature", status=403)

    result = await start_share_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ENTITIES: ["sensor.living_room_temperature"]},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "forbidden"}


async def test_share_flow_rejects_unknown_token(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entities_url: str,
    user_input: dict[str, Any],
) -> None:
    """A token the server does not know is caught on the connection step."""
    aioclient_mock.get(entities_url, status=401)

    result = await start_share_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)

    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.usefixtures("init_integration")
async def test_share_and_receive_the_same_server(
    hass: HomeAssistant,
    mock_put: AiohttpClientMocker,
    user_input: dict[str, Any],
) -> None:
    """Receiving from a server does not block sharing to it; they are separate entries."""
    result = await start_share_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)

    assert result["step_id"] == "share_entities"


# Publisher -------------------------------------------------------------------------------------


async def test_start_pushes_every_selected_entity(
    init_share: MockConfigEntry,
    mock_put: AiohttpClientMocker,
) -> None:
    """Setup pushes the current states, with their attributes and without last_changed."""
    pushed = puts(mock_put)

    temperature = pushed["/entities/sensor.living_room_temperature"]
    assert temperature["state"] == "21.5"
    assert temperature["attributes"]["unit_of_measurement"] == "°C"
    assert "last_changed" not in temperature
    assert "/entities/binary_sensor.window" in pushed


async def test_state_change_is_pushed(
    init_share: MockConfigEntry,
    hass: HomeAssistant,
    mock_put: AiohttpClientMocker,
) -> None:
    """A change of a selected entity is pushed; unknown and unavailable are not."""
    before = put_count(mock_put)

    hass.states.async_set("binary_sensor.window", "on", {"friendly_name": "Window"})
    await hass.async_block_till_done()
    assert put_count(mock_put) == before + 1
    assert puts(mock_put)["/entities/binary_sensor.window"]["state"] == "on"

    hass.states.async_set("binary_sensor.window", "unavailable")
    await hass.async_block_till_done()
    assert put_count(mock_put) == before + 1


async def test_unselected_entity_is_not_pushed(
    init_share: MockConfigEntry,
    hass: HomeAssistant,
    mock_put: AiohttpClientMocker,
) -> None:
    """Only the selected entities leave this Home Assistant."""
    before = put_count(mock_put)

    hass.states.async_set("sensor.secret", "42")
    await hass.async_block_till_done()

    assert put_count(mock_put) == before


async def test_heartbeat_repushes_unchanged_entities(
    init_share: MockConfigEntry,
    hass: HomeAssistant,
    mock_put: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Every HEARTBEAT_INTERVAL all selected entities are pushed again, so the server keeps them fresh."""
    before = put_count(mock_put)

    freezer.tick(HEARTBEAT_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert put_count(mock_put) == before + 2


async def test_attributes_are_made_json_safe(
    init_share: MockConfigEntry,
    hass: HomeAssistant,
    mock_put: AiohttpClientMocker,
) -> None:
    """Attributes such as datetimes are converted before they are sent."""
    moment = dt_util.utcnow()
    hass.states.async_set("binary_sensor.window", "on", {"since": moment})
    await hass.async_block_till_done()

    assert puts(mock_put)["/entities/binary_sensor.window"]["attributes"]["since"] == moment.isoformat()


async def test_rejected_token_starts_reauth(
    init_share: MockConfigEntry,
    hass: HomeAssistant,
    mock_put: AiohttpClientMocker,
    put_urls: list[str],
) -> None:
    """A 401 on a push opens the reauth flow."""
    mock_put.clear_requests()
    for url in put_urls:
        mock_put.put(url, status=401)

    hass.states.async_set("binary_sensor.window", "on")
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_server_error_is_survived(
    init_share: MockConfigEntry,
    hass: HomeAssistant,
    mock_put: AiohttpClientMocker,
    put_urls: list[str],
) -> None:
    """A failing server does not stop the publisher; the next change goes through once it recovers."""
    mock_put.clear_requests()
    for url in put_urls:
        mock_put.put(url, status=500)
    hass.states.async_set("binary_sensor.window", "on")
    await hass.async_block_till_done()

    mock_put.clear_requests()
    for url in put_urls:
        mock_put.put(url, status=204)
    hass.states.async_set("binary_sensor.window", "off")
    await hass.async_block_till_done()

    assert puts(mock_put)["/entities/binary_sensor.window"]["state"] == "off"
    assert init_share.runtime_data.publisher is not None
    assert init_share.runtime_data.publisher.last_error is None


async def test_options_change_what_is_shared(
    init_share: MockConfigEntry,
    hass: HomeAssistant,
    mock_put: AiohttpClientMocker,
) -> None:
    """After deselecting an entity in the options, its changes are no longer pushed."""
    result = await hass.config_entries.options.async_init(init_share.entry_id)
    assert result["step_id"] == "share"
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_ENTITIES: ["binary_sensor.window"]},
    )
    await hass.async_block_till_done()
    before = put_count(mock_put)

    hass.states.async_set("sensor.living_room_temperature", "22.0")
    await hass.async_block_till_done()

    assert put_count(mock_put) == before
