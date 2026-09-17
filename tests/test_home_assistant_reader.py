from __future__ import annotations

from jarvis.providers.home_assistant import HomeAssistantStateReader


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
