# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import hashlib
from datetime import datetime

import httpx
from loguru import logger

from jarvis.engine.proactive.collectors.base import CollectorBase
from jarvis.engine.proactive.schemas import ContextItem, ItemType, Priority
from jarvis.kernel.connectivity import is_offline_mode
from jarvis.kernel.contracts import CanonicalMemoryStore
from jarvis.kernel.error_collector import collector  # jrv: autofix
from jarvis.kernel.holmes_memory import CanonicalMemoryEvent, MemorySource
from jarvis.kernel.settings import settings


class HomeAssistantCollector(CollectorBase):
    """Collecteur proactif Home Assistant — alarme, fuites, fumée, etc."""

    name = "home_assistant"

    def __init__(self, canonical_memory: CanonicalMemoryStore | None = None) -> None:
        self._canonical_memory = canonical_memory
        self._recorded_event_ids: set[str] = set()

    async def _collect(self) -> list[ContextItem]:
        token = settings.home_assistant_token.get_secret_value()
        if is_offline_mode() or not token:
            return []

        base_url = settings.home_assistant_url.rstrip("/")
        headers = {"Authorization": f"Bearer {token}"}

        critical_entities: list[ContextItem] = []
        try:
            async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
                r = await client.get(f"{base_url}/api/states")
                if r.status_code != 200:
                    return []
                states = r.json()

            for state in states:
                entity_id = state.get("entity_id", "")
                domain = entity_id.split(".")[0] if "." in entity_id else ""
                current_state = state.get("state", "")
                friendly = state.get("attributes", {}).get("friendly_name", entity_id)

                alarm_states = ("triggered", "arming", "pending")
                if domain == "alarm_control_panel" and current_state in alarm_states:
                    item = ContextItem(
                            type=ItemType.NEWS,
                            title=f"🚨 ALARME DÉCLENCHÉE — {friendly}",
                            summary=f"L'alarme est en état **{current_state}**",
                            raw=str(state),
                            source="home_assistant",
                            timestamp=datetime.now(),
                            priority=Priority.HIGH,
                            metadata={"entity_id": entity_id, "state": current_state},
                    )
                    critical_entities.append(item)
                    await self._record_critical_event(item, state)

                elif domain == "binary_sensor" and current_state == "on":
                    device_class = state.get("attributes", {}).get("device_class", "")
                    if device_class in ("smoke", "gas", "moisture", "leak", "carbon_monoxide"):
                        item = ContextItem(
                                type=ItemType.NEWS,
                                title=f"⚠️ {friendly} — {device_class.upper()}",
                                summary=f"Capteur **{device_class}** activé",
                                raw=str(state),
                                source="home_assistant",
                                timestamp=datetime.now(),
                                priority=Priority.HIGH,
                                metadata={"entity_id": entity_id, "device_class": device_class},
                        )
                        critical_entities.append(item)
                        await self._record_critical_event(item, state)

            return critical_entities

        except Exception as e:
            collector.warning("JRV-PRO-001", "JRV-PRO-001", cause=e)
            logger.warning(f"HomeAssistantCollector error: {e}")
            return []

    async def _record_critical_event(self, item: ContextItem, state: dict) -> None:
        """Mémorise une alerte critique une seule fois par changement d'état."""
        if self._canonical_memory is None:
            return

        entity_id = str(state.get("entity_id", "unknown"))
        changed_at = str(state.get("last_changed", ""))
        fingerprint = f"{entity_id}|{state.get('state', '')}|{changed_at}"
        event_id = "ha_" + hashlib.sha256(fingerprint.encode()).hexdigest()[:24]
        if event_id in self._recorded_event_ids:
            return

        event = CanonicalMemoryEvent(
            event_id=event_id,
            source=MemorySource.HOME_ASSISTANT,
            content=f"{item.title}\n\n{item.summary}",
            metadata={
                "entity_id": entity_id,
                "state": state.get("state", ""),
                "last_changed": changed_at,
                "device_class": state.get("attributes", {}).get("device_class", ""),
            },
        )
        try:
            await self._canonical_memory.append_event(event)
            self._recorded_event_ids.add(event_id)
        except Exception as exc:  # noqa: BLE001 — l'alerte UI reste prioritaire
            collector.warning("JRV-PRO-001", "JRV-PRO-001", cause=exc)
            logger.warning("Home Assistant → Soul write failed", error=str(exc))
