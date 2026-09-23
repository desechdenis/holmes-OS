"""Lecture ciblée de Home Assistant pour les réponses Holmes.

Ce module est volontairement read-only. Les actions HA passent par une étape de
planification et de confirmation distincte.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import httpx


class HomeAssistantStateReader:
    """Interroge les états HA et produit un contexte court, lisible par Holmes."""

    _INTENT_WORDS = frozenset(
        {
            "alarme",
            "capteur",
            "capteurs",
            "chauffage",
            "clim",
            "consommation",
            "électricité",
            "humidite",
            "humidité",
            "lumiere",
            "lumières",
            "lumière",
            "porte",
            "portes",
            "presence",
            "présence",
            "temperature",
            "température",
        }
    )
    _IGNORED_WORDS = frozenset(
        {
            "dans",
            "de",
            "des",
            "du",
            "est",
            "et",
            "il",
            "la",
            "le",
            "les",
            "maison",
            "me",
            "moi",
            "pour",
            "quel",
            "quelle",
            "quoi",
            "sais",
            "sur",
            "tu",
            "une",
        }
    )

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        mode_entity: str = "",
        presence_entities: str = "",
        weather_entity: str = "",
        calendar_entities: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._mode_entity = mode_entity.strip()
        self._presence_entities = self._entity_list(presence_entities)
        self._weather_entity = weather_entity.strip()
        self._calendar_entities = self._entity_list(calendar_entities)

    @staticmethod
    def _entity_list(value: str) -> tuple[str, ...]:
        return tuple(item.strip() for item in value.split(",") if item.strip())

    async def _states(self) -> list[Mapping[str, Any]]:
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
            response = await client.get(f"{self._base_url}/api/states")
        response.raise_for_status()
        states = response.json()
        if not isinstance(states, list):
            return []
        return [state for state in states if isinstance(state, Mapping)]

    async def ambient_context(self) -> str:
        """Retourner quelques lignes de présent, sans inventer de valeur HA."""
        local_now = datetime.now().astimezone()
        lines = ["## Contexte ambiant", f"- Date locale : {local_now:%Y-%m-%d %H:%M}"]
        configured = (
            (self._mode_entity,)
            + self._presence_entities
            + ((self._weather_entity,) if self._weather_entity else ())
        )
        if not configured:
            return "\n".join(lines)
        try:
            states = {str(item.get("entity_id", "")): item for item in await self._states()}
        except (httpx.HTTPError, TimeoutError):
            lines.append("- Home Assistant : indisponible")
            return "\n".join(lines)

        labels = [(self._mode_entity, "Mode maison")]
        labels.extend((entity_id, "Présence") for entity_id in self._presence_entities)
        labels.append((self._weather_entity, "Météo actuelle"))
        for entity_id, label in labels:
            if not entity_id:
                continue
            state = states.get(entity_id)
            if state is None:
                continue
            attrs = state.get("attributes", {})
            attrs = attrs if isinstance(attrs, Mapping) else {}
            name = str(attrs.get("friendly_name") or label)
            value = str(state.get("state", "inconnu"))
            if entity_id == self._weather_entity and attrs.get("temperature") is not None:
                unit = str(attrs.get("temperature_unit") or "")
                value = f"{value}, {attrs['temperature']} {unit}".strip()
            lines.append(f"- {name} : {value}")
        return "\n".join(lines)

    @classmethod
    def is_relevant(cls, query: str) -> bool:
        words = set(re.findall(r"[\w-]+", query.casefold(), flags=re.UNICODE))
        return bool(words & cls._INTENT_WORDS)

    async def lookup(self, query: str, limit: int = 6) -> str | None:
        if not self.is_relevant(query):
            return None

        states = await self._states()

        query_words = self._query_words(query)
        matches = sorted(
            (state for state in states if isinstance(state, Mapping)),
            key=lambda state: self._score(state, query_words),
            reverse=True,
        )
        selected = [state for state in matches if self._score(state, query_words) > 0][:limit]
        if not selected:
            return None

        lines = ["## État Home Assistant en direct"]
        for state in selected:
            entity_id = str(state.get("entity_id", ""))
            value = str(state.get("state", ""))
            attrs = state.get("attributes", {})
            attrs = attrs if isinstance(attrs, Mapping) else {}
            name = str(attrs.get("friendly_name") or entity_id)
            unit = str(attrs.get("unit_of_measurement") or "")
            display_value = f"{value} {unit}".strip()
            lines.append(f"- {name} ({entity_id}) : {display_value}")
        return "\n".join(lines)

    @classmethod
    def _query_words(cls, query: str) -> set[str]:
        return {
            word
            for word in re.findall(r"[\w-]+", query.casefold(), flags=re.UNICODE)
            if len(word) > 2 and word not in cls._IGNORED_WORDS
        }

    @classmethod
    def _score(cls, state: Mapping[str, Any], query_words: set[str]) -> int:
        entity_id = str(state.get("entity_id", ""))
        attrs = state.get("attributes", {})
        attrs = attrs if isinstance(attrs, Mapping) else {}
        friendly = str(attrs.get("friendly_name", ""))
        haystack = f"{entity_id} {friendly}".casefold()
        score = sum(word in haystack for word in query_words)
        domain = entity_id.split(".", 1)[0]
        if {"temperature", "température"} & query_words and domain == "sensor":
            score += 1
        if {"lumiere", "lumière", "lumières"} & query_words and domain == "light":
            score += 2
        if {"porte", "portes"} & query_words and domain in {"binary_sensor", "cover"}:
            score += 2
        if "alarme" in query_words and domain == "alarm_control_panel":
            score += 2
        return score
