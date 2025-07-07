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
                
                # Validate response structure
                if not isinstance(data, dict):
                    raise APIError("Invalid API response format: expected dict")
                
                if "readings" not in data:
                    raise APIError("Invalid API response: missing 'readings' field")
                
                if not isinstance(data["readings"], list):
                    raise APIError("Invalid API response: 'readings' must be a list")
                
                # Check for empty readings array
                if not data["readings"]:
                    _LOGGER.info("API returned empty readings array")
                    # Return empty data structure instead of raising an error
                    return {"readings": [], "model": data.get("model"), "serialNumber": data.get("serialNumber"), "unit": data.get("unit")}
                
                # Validate readings format
                for i, reading in enumerate(data["readings"]):
                    if not isinstance(reading, list) or len(reading) != 2:
                        raise APIError(f"Invalid reading format at index {i}: expected [timestamp, value]")
                    
                    if not isinstance(reading[0], (int, float)):
                        raise APIError(f"Invalid timestamp format at index {i}: expected number")
                    
                    if not isinstance(reading[1], (int, float)):
                        raise APIError(f"Invalid value format at index {i}: expected number")
                
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

    async def async_get_readings_range(
        self, start_date: datetime, end_date: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Get water meter readings for a specific date range."""
        data = await self.async_get_readings(start_date, end_date)
        
        if not data or "readings" not in data or not data["readings"]:
            return []

        # Convert readings to structured format
        readings = []
        for reading in data["readings"]:
            readings.append({
                "model": data.get("model"),
                "serial_number": data.get("serialNumber"),
                "unit": data.get("unit"),
                "timestamp": reading[0],
                "value": reading[1],
            })
        
        # Sort by timestamp (oldest first)
        readings.sort(key=lambda x: x["timestamp"])
        return readings

    async def async_get_readings_since(
        self, since_timestamp: int
    ) -> list[dict[str, Any]]:
        """Get all readings since a specific timestamp."""
        # Calculate start date from timestamp
        start_date = datetime.fromtimestamp(since_timestamp)
        
        # Get readings from that date to now
        readings = await self.async_get_readings_range(start_date)
        
        # Filter to only include readings after the specified timestamp
        return [r for r in readings if r["timestamp"] > since_timestamp]

    def calculate_usage_from_readings(
        self, readings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Calculate usage between consecutive readings."""
        if len(readings) < 2:
            return []
        
        usage_data = []
        for i in range(1, len(readings)):
            prev_reading = readings[i - 1]
            curr_reading = readings[i]
            
            # Calculate usage (difference in values)
            usage = curr_reading["value"] - prev_reading["value"]
            
            # Calculate time difference in hours
            time_diff = (curr_reading["timestamp"] - prev_reading["timestamp"]) / 3600
            
            usage_data.append({
                "start_timestamp": prev_reading["timestamp"],
                "end_timestamp": curr_reading["timestamp"],
                "start_value": prev_reading["value"],
                "end_value": curr_reading["value"],
                "usage": usage,
                "duration_hours": time_diff,
                "unit": curr_reading["unit"],
            })
        
        return usage_data

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