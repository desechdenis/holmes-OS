"""Home Assistant conversation entity backed by Holmes OS."""

from __future__ import annotations

from typing import Any

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.intent import IntentResponse

from .client import (  # noqa: TID252 - HA custom component convention
    ConversationReply,
    HolmesClient,
    HolmesConversationService,
)
from .const import (  # noqa: TID252 - HA custom component convention
    CONF_FALLBACK_AGENT,
    DEFAULT_FALLBACK_AGENT,
    DOMAIN,
    TITLE,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([HolmesConversationEntity(hass, entry)])


class HolmesConversationEntity(conversation.ConversationEntity):
    _attr_has_entity_name = True
    _attr_name = TITLE
    _attr_supports_streaming = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = entry.entry_id
        client: HolmesClient = hass.data[DOMAIN][entry.entry_id]
        self._service = HolmesConversationService(client, self._fallback)

    @property
    def supported_languages(self) -> list[str]:
        return [conversation.MATCH_ALL]

    async def _fallback(
        self, text: str, conversation_id: str | None, language: str
    ) -> ConversationReply:
        result = await conversation.async_converse(
            hass=self.hass,
            text=text,
            conversation_id=conversation_id,
            context=self._context,
            language=language,
            agent_id=self._entry.data.get(CONF_FALLBACK_AGENT, DEFAULT_FALLBACK_AGENT),
        )
        speech = result.response.speech.get("plain", {}).get("speech", "")
        return ConversationReply(speech, result.conversation_id)

    async def _async_handle_message(  # noqa: ANN401 - HA model types vary by release
        self, user_input: Any, chat_log: Any  # noqa: ANN401
    ) -> conversation.ConversationResult:
        result = await self._service.process(
            user_input.text,
            user_input.conversation_id,
            user_input.language,
        )
        response = IntentResponse(language=user_input.language)
        response.async_set_speech(result.text)
        return conversation.ConversationResult(
            response=response,
            conversation_id=result.conversation_id,
        )
