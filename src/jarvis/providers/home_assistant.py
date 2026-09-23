"""Lecture ciblée de Home Assistant pour les réponses Holmes.

Ce module est volontairement read-only. Les actions HA passent par une étape de
planification et de confirmation distincte.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

import httpx

READ_ONLY_SERVICES = frozenset(
    {
        ("weather", "get_forecasts"),
        ("calendar", "get_events"),
    }
)


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

    async def call_read_only_service(
        self, domain: str, service: str, data: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Appeler un service HA uniquement s'il appartient à la liste blanche fermée."""
        if (domain, service) not in READ_ONLY_SERVICES:
            raise ValueError(f"Home Assistant service refused: {domain}.{service}")
        headers = {"Authorization": f"Bearer {self._token}"}
        url = f"{self._base_url}/api/services/{domain}/{service}"
        async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
            response = await client.post(url, params={"return_response": "true"}, json=dict(data))
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, Mapping) else {}

    async def weather_forecast(self) -> str | None:
        if not self._weather_entity:
            return None
        payload = await self.call_read_only_service(
            "weather",
            "get_forecasts",
            {"entity_id": self._weather_entity, "type": "daily"},
        )
        service_response = payload.get("service_response", {})
        service_response = service_response if isinstance(service_response, Mapping) else {}
        entity_result = service_response.get(self._weather_entity, {})
        entity_result = entity_result if isinstance(entity_result, Mapping) else {}
        forecast = entity_result.get("forecast", [])
        if not isinstance(forecast, list) or not forecast:
            return None
        lines = []
        for item in forecast[:4]:
            if not isinstance(item, Mapping):
                continue
            when = str(item.get("datetime", "date inconnue"))[:10]
            condition = str(item.get("condition", "état inconnu"))
            temperature = item.get("temperature")
            suffix = f", {temperature}°" if temperature is not None else ""
            lines.append(f"- {when} : {condition}{suffix}")
        return "\n".join(lines) or None

    async def calendar_events(self, days_ahead: int = 7) -> str | None:
        if not self._calendar_entities:
            return None
        start = datetime.now().astimezone()
        end = start + timedelta(days=days_ahead)
        payload = await self.call_read_only_service(
            "calendar",
            "get_events",
            {
                "entity_id": list(self._calendar_entities),
                "start_date_time": start.isoformat(),
                "end_date_time": end.isoformat(),
            },
        )
        service_response = payload.get("service_response", {})
        service_response = service_response if isinstance(service_response, Mapping) else {}
        lines: list[str] = []
        for entity_id in self._calendar_entities:
            entity_result = service_response.get(entity_id, {})
            entity_result = entity_result if isinstance(entity_result, Mapping) else {}
            events = entity_result.get("events", [])
            if not isinstance(events, list):
                continue
            for event in events:
                if not isinstance(event, Mapping):
                    continue
                start_value = str(event.get("start", "date inconnue"))
                summary = str(event.get("summary", "événement"))
                lines.append(f"- {start_value} : {summary}")
        return "\n".join(lines[:8]) or None

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
