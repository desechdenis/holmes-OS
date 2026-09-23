"""Holmes OS integration setup."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

from .client import HolmesClient  # noqa: TID252 - HA custom component convention
from .const import (  # noqa: TID252 - HA custom component convention
    CONF_CERTIFICATE_FINGERPRINT,
    CONF_TOKEN,
    CONF_URL,
    DOMAIN,
    PLATFORMS,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = HolmesClient(
        async_get_clientsession(hass),
        entry.data[CONF_URL],
        entry.data[CONF_TOKEN],
        entry.data[CONF_CERTIFICATE_FINGERPRINT],
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
