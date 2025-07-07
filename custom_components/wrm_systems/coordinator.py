"""DataUpdateCoordinator for WRM-Systems integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WRMSystemsAPIClient, APIError, InvalidAuth
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class WRMSystemsDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the WRM-Systems API."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.config_entry = config_entry
        self.api = WRMSystemsAPIClient(
            session=async_get_clientsession(hass),
            token=config_entry.data[CONF_TOKEN],
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""
        try:
            data = await self.api.async_get_latest_reading()
            _LOGGER.debug("Successfully fetched data: %s", data)
            return data
        except InvalidAuth as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except APIError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err