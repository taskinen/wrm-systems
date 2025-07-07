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
    CONF_MAX_DATA_AGE_HOURS,
    DEFAULT_SCAN_INTERVAL, 
    DEFAULT_MAX_DATA_AGE_HOURS,
    MIN_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_MAX_DATA_AGE_HOURS,
    MAX_MAX_DATA_AGE_HOURS,
    validate_scan_interval,
    validate_max_data_age_hours,
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
        vol.Optional(
            CONF_MAX_DATA_AGE_HOURS,
            default=DEFAULT_MAX_DATA_AGE_HOURS
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_MAX_DATA_AGE_HOURS, max=MAX_MAX_DATA_AGE_HOURS)
        ),
    }
)


class ConfigFlow(config_entries.ConfigFlow):
    """Handle a config flow for WRM-Systems."""

    VERSION = 1

    @property
    def domain(self) -> str:
        """Return the domain."""
        return DOMAIN

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
        
        # Validate max data age hours
        if CONF_MAX_DATA_AGE_HOURS in user_input:
            max_data_age_hours = user_input[CONF_MAX_DATA_AGE_HOURS]
            if not validate_max_data_age_hours(max_data_age_hours):
                errors[CONF_MAX_DATA_AGE_HOURS] = "max_data_age_hours_invalid"

        if not errors:
            try:
                await self._test_credentials(user_input[CONF_TOKEN])
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except APIError as err:
                _LOGGER.warning("API error during setup: %s", err)
                if "network" in str(err).lower() or "timeout" in str(err).lower():
                    errors["base"] = "cannot_connect"
                else:
                    errors["base"] = "api_error"
            except Exception as err:
                _LOGGER.exception("Unexpected exception during setup: %s", err)
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
        
        try:
            # Test connection using the robust test method
            success = await api_client.async_test_connection()
            if not success:
                raise APIError("Failed to connect to API - connection test returned False")
        except InvalidAuth:
            # Re-raise authentication errors directly
            raise
        except APIError:
            # Re-raise API errors directly  
            raise
        except Exception as err:
            # Convert unexpected errors to API errors with context
            raise APIError(f"Connection test failed with unexpected error: {err}") from err

