"""UI configuration flow for Holmes OS."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_TOKEN, CONF_URL

from .client import certificate_fingerprint  # noqa: TID252 - HA custom component convention
from .const import (  # noqa: TID252 - HA custom component convention
    CONF_CERTIFICATE_FINGERPRINT,
    CONF_FALLBACK_AGENT,
    DEFAULT_FALLBACK_AGENT,
    DOMAIN,
    TITLE,
)


class HolmesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(  # noqa: ANN401 - FlowResult varies across HA releases
        self, user_input: dict[str, Any] | None = None
    ) -> Any:  # noqa: ANN401
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                certificate_fingerprint(user_input[CONF_CERTIFICATE_FINGERPRINT])
            except ValueError:
                errors[CONF_CERTIFICATE_FINGERPRINT] = "invalid_fingerprint"
            else:
                await self.async_set_unique_id(user_input[CONF_URL].rstrip("/"))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=TITLE, data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_URL): str,
                vol.Required(CONF_TOKEN): str,
                vol.Required(CONF_CERTIFICATE_FINGERPRINT): str,
                vol.Required(CONF_FALLBACK_AGENT, default=DEFAULT_FALLBACK_AGENT): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
