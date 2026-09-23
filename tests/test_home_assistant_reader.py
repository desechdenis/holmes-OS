from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from jarvis.providers.home_assistant import READ_ONLY_SERVICES, HomeAssistantStateReader


def test_home_assistant_reader_only_targets_home_state_questions() -> None:
    assert HomeAssistantStateReader.is_relevant("Quelle est la température du salon ?")
    assert HomeAssistantStateReader.is_relevant("Les lumières sont allumées ?")
    assert not HomeAssistantStateReader.is_relevant("Combien de CT dans Body ?")


def test_home_assistant_reader_scores_matching_entities_first() -> None:
    query_words = HomeAssistantStateReader._query_words("température salon")
    salon_temperature = {
        "entity_id": "sensor.salon_temperature",
        "attributes": {"friendly_name": "Température Salon"},
    }
    garage_door = {
        "entity_id": "binary_sensor.garage_door",
        "attributes": {"friendly_name": "Porte garage"},
    }

    assert HomeAssistantStateReader._score(salon_temperature, query_words) > (
        HomeAssistantStateReader._score(garage_door, query_words)
    )


@pytest.mark.asyncio
async def test_ambient_context_uses_only_configured_entities() -> None:
    reader = HomeAssistantStateReader(
        "https://ha.invalid",
        "token-factice",
        mode_entity="input_select.mode",
        presence_entities="person.one, person.two",
        weather_entity="weather.home",
    )
    states = [
        {"entity_id": "input_select.mode", "state": "Présent", "attributes": {}},
        {"entity_id": "person.one", "state": "home", "attributes": {"friendly_name": "A"}},
        {"entity_id": "sensor.private", "state": "secret", "attributes": {}},
        {
            "entity_id": "weather.home",
            "state": "sunny",
            "attributes": {"temperature": 21, "temperature_unit": "°C"},
        },
    ]
    with patch.object(reader, "_states", AsyncMock(return_value=states)):
        context = await reader.ambient_context()

    assert "Mode maison : Présent" in context
    assert "A : home" in context
    assert "sunny, 21 °C" in context
    assert "secret" not in context


@pytest.mark.asyncio
async def test_ambient_context_falls_back_cleanly_when_ha_is_unavailable() -> None:
    reader = HomeAssistantStateReader(
        "https://ha.invalid", "token-factice", mode_entity="input_select.mode"
    )
    with patch.object(reader, "_states", AsyncMock(side_effect=httpx.ConnectError("hors ligne"))):
        context = await reader.ambient_context()

    assert "Date locale" in context
    assert "Home Assistant : indisponible" in context


@pytest.mark.asyncio
async def test_read_only_service_allowlist_refuses_every_other_service() -> None:
    reader = HomeAssistantStateReader("https://ha.invalid", "token-factice")

    assert READ_ONLY_SERVICES == {
        ("weather", "get_forecasts"),
        ("calendar", "get_events"),
    }
    with pytest.raises(ValueError, match="refused"):
        await reader.call_read_only_service("light", "turn_on", {"entity_id": "light.test"})
