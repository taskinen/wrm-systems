"""API client for WRM-Systems water meter."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from aiohttp import ClientSession

from .const import API_BASE_URL

_LOGGER = logging.getLogger(__name__)


class WRMSystemsAPIClient:
    """API client for WRM-Systems water meter."""

    def __init__(self, session: ClientSession, token: str) -> None:
        """Initialize the API client."""
        self._session = session
        self._token = token
        self._headers = {"Authorization": f"Bearer {token}"}

    async def async_get_readings(
        self, start_date: datetime | None = None, end_date: datetime | None = None
    ) -> dict[str, Any]:
        """Get water meter readings from the API."""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=1)
        
        params = {"startDate": start_date.strftime("%Y-%m-%d")}
        if end_date:
            params["endDate"] = end_date.strftime("%Y-%m-%d")

        _LOGGER.debug("Fetching readings with params: %s", params)

        try:
            async with self._session.get(
                API_BASE_URL, headers=self._headers, params=params
            ) as response:
                if response.status == 401:
                    raise InvalidAuth("Invalid authentication token")
                elif response.status != 200:
                    raise APIError(f"API returned status {response.status}")

                data = await response.json()
                _LOGGER.debug("API response: %s", data)
                return data

        except aiohttp.ClientError as err:
            raise APIError(f"Error connecting to API: {err}") from err

    async def async_get_latest_reading(self) -> dict[str, Any]:
        """Get the latest water meter reading."""
        data = await self.async_get_readings()
        
        if not data or "readings" not in data or not data["readings"]:
            raise APIError("No readings available")

        # Find the most recent reading
        latest_reading = max(data["readings"], key=lambda x: x[0])
        
        return {
            "model": data.get("model"),
            "serial_number": data.get("serialNumber"),
            "unit": data.get("unit"),
            "timestamp": latest_reading[0],
            "value": latest_reading[1],
        }

    async def async_test_connection(self) -> bool:
        """Test if the API connection is working."""
        try:
            await self.async_get_readings()
            return True
        except (APIError, InvalidAuth):
            return False


class APIError(Exception):
    """Exception raised when API returns an error."""


class InvalidAuth(Exception):
    """Exception raised when authentication fails."""