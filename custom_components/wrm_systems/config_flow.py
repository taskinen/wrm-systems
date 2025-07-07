"""Config flow for WRM-Systems integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_TOKEN
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TOKEN): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for WRM-Systems."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            await self._test_credentials(user_input[CONF_TOKEN])
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(title="WRM-Systems", data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def _test_credentials(self, token: str) -> None:
        """Validate the user input allows us to connect."""
        session = async_get_clientsession(self.hass)
        
        headers = {"Authorization": f"Bearer {token}"}
        url = "https://wmd.wrm-systems.fi/api/watermeter"
        
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 401:
                    raise InvalidAuth
                elif response.status != 200:
                    raise CannotConnect
                
                data = await response.json()
                if not data or "readings" not in data:
                    raise InvalidAuth
                    
        except aiohttp.ClientError as err:
            raise CannotConnect from err


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""