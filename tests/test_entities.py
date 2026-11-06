"""Tests for the mirrored sensor and binary sensor entities."""

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hofmaetteli_telemetry.coordinator.base import UPDATE_INTERVAL
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

TEMPERATURE = "sensor.telemetry_example_org_outdoor_temperature"
CONDITION = "sensor.telemetry_example_org_weather_condition"
DOOR = "binary_sensor.telemetry_example_org_front_door"


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(UPDATE_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("init_integration")
async def test_numeric_sensor_takes_unit_and_classes_from_the_remote(hass: HomeAssistant) -> None:
    """Unit, device class and state class come from the remote attributes, not from YAML."""
    state = hass.states.get(TEMPERATURE)

    assert state is not None
    assert state.state == "12.5"
    assert state.attributes["unit_of_measurement"] == "°C"
    assert state.attributes["device_class"] == "temperature"
    assert state.attributes["state_class"] == "measurement"
    assert state.attributes["friendly_name"] == "telemetry.example.org Outdoor temperature"


@pytest.mark.usefixtures("init_integration")
async def test_device_is_named_after_the_server_host(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry, entity_registry: er.EntityRegistry
) -> None:
    """The device name, and the entity IDs derived from it, ignore the entry title."""
    entity = entity_registry.async_get(TEMPERATURE)

    assert entity is not None
    device = device_registry.async_get(entity.device_id)
    assert device is not None
    assert device.name == "telemetry.example.org"


@pytest.mark.usefixtures("init_integration")
async def test_unmapped_attributes_and_freshness_are_passed_through(hass: HomeAssistant) -> None:
    """Remote attributes without an entity property, and the server's stale flag, stay visible."""
    temperature = hass.states.get(TEMPERATURE)
    condition = hass.states.get(CONDITION)

    assert temperature.attributes["battery"] == 87
    assert temperature.attributes["remote_entity_id"] == "sensor.outdoor_temperature"
    assert temperature.attributes["stale"] is False
    assert condition.attributes["stale"] is True


@pytest.mark.usefixtures("init_integration")
async def test_text_sensor_and_binary_sensor(hass: HomeAssistant) -> None:
    """A sensor without a unit keeps its text state, and a binary sensor maps on and off."""
    assert hass.states.get(CONDITION).state == "sunny"

    door = hass.states.get(DOOR)
    assert door.state == "on"
    assert door.attributes["device_class"] == "door"


async def test_numeric_sensor_with_text_state_is_unknown(
    init_integration: MockConfigEntry,
    hass: HomeAssistant,
    mock_server: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    api_response: list[dict[str, Any]],
    entities_url: str,
) -> None:
    """A temperature that reports `unavailable` on the sender shows as unknown, not as an error."""
    api_response[0]["state"] = "unavailable"
    mock_server.clear_requests()
    mock_server.get(entities_url, json=api_response)

    await _poll(hass, freezer)

    assert hass.states.get(TEMPERATURE).state == STATE_UNKNOWN


async def test_entity_removed_on_server_becomes_unavailable(
    init_integration: MockConfigEntry,
    hass: HomeAssistant,
    mock_server: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    api_response: list[dict[str, Any]],
    entities_url: str,
) -> None:
    """An entity the server stops reporting goes unavailable while the others keep working."""
    mock_server.clear_requests()
    mock_server.get(entities_url, json=api_response[1:])

    await _poll(hass, freezer)

    assert hass.states.get(TEMPERATURE).state == STATE_UNAVAILABLE
    assert hass.states.get(CONDITION).state == "sunny"


async def test_entities_go_unavailable_when_the_poll_fails(
    init_integration: MockConfigEntry,
    hass: HomeAssistant,
    mock_server: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    entities_url: str,
) -> None:
    """A failing server makes every entity unavailable until it answers again."""
    mock_server.clear_requests()
    mock_server.get(entities_url, status=500)

    await _poll(hass, freezer)

    assert hass.states.get(TEMPERATURE).state == STATE_UNAVAILABLE
    assert hass.states.get(DOOR).state == STATE_UNAVAILABLE


async def test_rejected_token_starts_reauth(
    init_integration: MockConfigEntry,
    hass: HomeAssistant,
    mock_server: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    entities_url: str,
) -> None:
    """A 401 on a poll opens the reauth flow instead of retrying forever."""
    mock_server.clear_requests()
    mock_server.get(entities_url, status=401)

    await _poll(hass, freezer)

    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]
    assert init_integration.state is ConfigEntryState.LOADED
