"""Shared fixtures for the hofmaetteli_telemetry tests."""

from collections.abc import Generator
import copy
import logging
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hofmaetteli_telemetry.const import CONF_ENTITIES, CONF_MODE, DOMAIN, MODE_RECEIVE, MODE_SHARE
from homeassistant.const import CONF_API_TOKEN, CONF_URL, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant

SERVER_URL = "https://telemetry.example.org"
ENTITIES_URL = f"{SERVER_URL}/entities"
TOKEN = "read-token"

# The shape `GET /entities?full=true` returns, taken from the server's LatestResponse model.
API_RESPONSE: list[dict[str, Any]] = [
    {
        "entity_id": "sensor.outdoor_temperature",
        "state": "12.5",
        "attributes": {
            "friendly_name": "Outdoor temperature",
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "state_class": "measurement",
            "battery": 87,
        },
        "ts": "2026-11-06T08:00:00+00:00",
        "stale": False,
    },
    {
        "entity_id": "sensor.weather_condition",
        "state": "sunny",
        "attributes": {"friendly_name": "Weather condition"},
        "ts": "2026-11-06T08:00:00+00:00",
        "stale": True,
    },
    {
        "entity_id": "binary_sensor.front_door",
        "state": "on",
        "attributes": {"friendly_name": "Front door", "device_class": "door"},
        "ts": "2026-11-06T08:00:00+00:00",
        "stale": False,
    },
]
SELECTED = ["sensor.outdoor_temperature", "sensor.weather_condition", "binary_sensor.front_door"]
SHARED = ["sensor.living_room_temperature", "binary_sensor.window"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom integrations in every test."""


@pytest.fixture(autouse=True)
def fail_on_deprecation_report(caplog: pytest.LogCaptureFixture) -> Generator[None]:
    """Fail a test when Home Assistant logs a deprecation this integration caused."""
    yield
    reports = [
        message
        for record in [*caplog.get_records("setup"), *caplog.get_records("call")]
        if record.levelno >= logging.WARNING
        and DOMAIN in (message := record.getMessage())
        and message.startswith(("Detected that custom integration", "The deprecated"))
    ]
    assert not reports, "\n".join(reports)


@pytest.fixture
def api_response() -> list[dict[str, Any]]:
    """Return a copy of the server response, safe for a test to modify."""
    return copy.deepcopy(API_RESPONSE)


@pytest.fixture
def entities_url() -> str:
    """Return the URL the integration polls."""
    return ENTITIES_URL


@pytest.fixture
def user_input() -> dict[str, Any]:
    """Return what a user types into the first config flow step, with sloppy whitespace and a trailing slash."""
    return {CONF_URL: f"  {SERVER_URL}/ ", CONF_API_TOKEN: TOKEN, CONF_VERIFY_SSL: True}


@pytest.fixture
def mock_server(
    aioclient_mock: AiohttpClientMocker,
    api_response: list[dict[str, Any]],
) -> AiohttpClientMocker:
    """
    Answer the entities request with the api_response fixture.

    Returns:
        The mocker, so a test can change the response or count calls.

    """
    aioclient_mock.get(ENTITIES_URL, json=api_response)
    return aioclient_mock


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a config entry that mirrors every entity in API_RESPONSE."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Receiving from telemetry.example.org",
        data={CONF_URL: SERVER_URL, CONF_API_TOKEN: TOKEN, CONF_VERIFY_SSL: True, CONF_MODE: MODE_RECEIVE},
        options={CONF_ENTITIES: SELECTED},
    )


@pytest.fixture
def share_entry() -> MockConfigEntry:
    """Return a config entry that shares two local sensors."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Sharing to telemetry.example.org",
        data={CONF_URL: SERVER_URL, CONF_API_TOKEN: "write-token", CONF_VERIFY_SSL: True, CONF_MODE: MODE_SHARE},
        options={CONF_ENTITIES: SHARED},
    )


@pytest.fixture
def local_states(hass: HomeAssistant) -> None:
    """Create the local entities a share entry pushes."""
    hass.states.async_set(
        "sensor.living_room_temperature",
        "21.5",
        {"unit_of_measurement": "°C", "device_class": "temperature", "friendly_name": "Living room"},
    )
    hass.states.async_set("binary_sensor.window", "off", {"friendly_name": "Window"})


@pytest.fixture
def put_urls() -> list[str]:
    """Return the URLs a share entry pushes its entities to."""
    return [f"{ENTITIES_URL}/{entity_id}" for entity_id in SHARED]


@pytest.fixture
def mock_put(aioclient_mock: AiohttpClientMocker, put_urls: list[str]) -> AiohttpClientMocker:
    """
    Accept every push with 204, and answer the token check of a write-only token with 403.

    Returns:
        The mocker, so a test can inspect the pushes.

    """
    for url in put_urls:
        aioclient_mock.put(url, status=204)
    aioclient_mock.get(ENTITIES_URL, status=403)
    return aioclient_mock


@pytest.fixture
async def init_share(
    hass: HomeAssistant,
    local_states: None,
    mock_put: AiohttpClientMocker,
    share_entry: MockConfigEntry,
) -> MockConfigEntry:
    """
    Set up a share entry and let it push its initial states.

    Returns:
        The config entry, now loaded.

    """
    share_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(share_entry.entry_id)
    await hass.async_block_till_done()
    return share_entry


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_server: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> MockConfigEntry:
    """
    Set up the integration from a config entry.

    Returns:
        The config entry, now loaded.

    """
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
