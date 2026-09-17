"""Lecture ciblée de Home Assistant pour les réponses Holmes.

Ce module est volontairement read-only. Les actions HA passent par une étape de
planification et de confirmation distincte.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
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
            "dans", "de", "des", "du", "est", "et", "il", "la", "le", "les", "maison",
            "me", "moi", "pour", "quel", "quelle", "quoi", "sais", "sur", "tu", "une",
        }
    )

    def __init__(self, base_url: str, token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token

    @classmethod
    def is_relevant(cls, query: str) -> bool:
        words = set(re.findall(r"[\w-]+", query.casefold(), flags=re.UNICODE))
        return bool(words & cls._INTENT_WORDS)

    async def lookup(self, query: str, limit: int = 6) -> str | None:
        if not self.is_relevant(query):
            return None

        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
            response = await client.get(f"{self._base_url}/api/states")
        response.raise_for_status()
        states = response.json()
        if not isinstance(states, list):
            return None

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
