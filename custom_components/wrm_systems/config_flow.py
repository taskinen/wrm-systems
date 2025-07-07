"""Config flow for WRM-Systems integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_TOKEN
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import InvalidAuth, APIError, WRMSystemsAPIClient
from .const import (
    DOMAIN, 
    CONF_SCAN_INTERVAL, 
    DEFAULT_SCAN_INTERVAL, 
    MIN_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
    validate_scan_interval
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TOKEN): str,
        vol.Optional(
            CONF_SCAN_INTERVAL, 
            default=DEFAULT_SCAN_INTERVAL
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
        ),
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

        # Validate scan interval
        if CONF_SCAN_INTERVAL in user_input:
            scan_interval = user_input[CONF_SCAN_INTERVAL]
            if not validate_scan_interval(scan_interval):
                errors[CONF_SCAN_INTERVAL] = "scan_interval_invalid"

        if not errors:
            try:
                await self._test_credentials(user_input[CONF_TOKEN])
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except APIError:
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
        api_client = WRMSystemsAPIClient(session, token)
        
        # Test connection using the robust test method
        if not await api_client.async_test_connection():
            raise APIError("Failed to connect to API")

