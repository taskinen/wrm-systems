"""API client for WRM-Systems water meter."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from aiohttp import ClientSession

from .const import API_BASE_URL, MAX_RETRIES, RETRY_DELAY, REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class WRMSystemsAPIClient:
    """API client for WRM-Systems water meter."""

    def __init__(self, session: ClientSession, token: str) -> None:
        """Initialize the API client."""
        self._session = session
        self._token = token
        self._headers = {"Authorization": f"Bearer {token}"}
        self._last_request_time = 0.0
        self._min_request_interval = 1.0  # Minimum 1 second between requests

    def _sanitize_for_logging(self, data: dict[str, Any]) -> dict[str, Any]:
        """Remove sensitive data from logs."""
        if not isinstance(data, dict):
            return data
        
        sanitized = data.copy()
        # Remove any potential sensitive fields
        sensitive_fields = ["token", "auth", "password", "key"]
        for field in sensitive_fields:
            if field in sanitized:
                sanitized[field] = "***"
        
        return sanitized

    async def _rate_limit(self) -> None:
        """Ensure minimum time between API requests."""
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self._last_request_time
        
        if time_since_last < self._min_request_interval:
            sleep_time = self._min_request_interval - time_since_last
            await asyncio.sleep(sleep_time)
        
        self._last_request_time = asyncio.get_event_loop().time()

    async def _make_request_with_retry(
        self, url: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make HTTP request with retry logic and proper error handling."""
        # Apply rate limiting before making request
        await self._rate_limit()
        
        last_exception = None
        
        for attempt in range(MAX_RETRIES):
            try:
                await self._rate_limit()  # Apply rate limiting

                timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
                async with self._session.get(
                    url, headers=self._headers, params=params, timeout=timeout
                ) as response:
                    if response.status == 401:
                        raise InvalidAuth("Invalid authentication token")
                    elif response.status == 429:
                        # Add rate limiting handling
                        wait_time = RETRY_DELAY * (2 ** attempt)
                        _LOGGER.warning("Rate limited, waiting %d seconds", wait_time)
                        await asyncio.sleep(wait_time)
                        continue
                    elif response.status != 200:
                        raise APIError(f"API returned status {response.status}: {await response.text()}")

                    try:
                        data = await response.json()
                    except aiohttp.ContentTypeError as err:
                        raise APIError(f"Invalid JSON response from API: {err}") from err
                    except Exception as err:
                        raise APIError(f"Failed to parse JSON response: {err}") from err
                    
                    _LOGGER.debug("API response (attempt %d): %s", attempt + 1, self._sanitize_for_logging(data))
                    return data

            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                last_exception = err
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                    _LOGGER.warning(
                        "API request failed (attempt %d/%d), retrying in %d seconds: %s",
                        attempt + 1, MAX_RETRIES, wait_time, err
                    )
                    await asyncio.sleep(wait_time)
                else:
                    _LOGGER.error("API request failed after %d attempts: %s", MAX_RETRIES, err)
            except (InvalidAuth, APIError):
                # Don't retry auth errors or API errors
                raise
            except Exception as err:
                last_exception = err
                _LOGGER.error("Unexpected error during API request: %s", err)
                break
        
        # If we get here, all retries failed
        raise APIError(f"Network error after {MAX_RETRIES} attempts: {last_exception}") from last_exception

    async def async_get_readings(
        self, start_date: datetime | None = None, end_date: datetime | None = None
    ) -> dict[str, Any]:
        """Get water meter readings from the API."""
        if start_date is None:
            start_date = datetime.now(timezone.utc) - timedelta(days=1)
        
        # Ensure timezone awareness
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        
        params = {"startDate": start_date.strftime("%Y-%m-%d")}
        if end_date:
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=timezone.utc)
            params["endDate"] = end_date.strftime("%Y-%m-%d")

        _LOGGER.debug("Fetching readings with params: %s", params)

        try:
            data = await self._make_request_with_retry(API_BASE_URL, params)
                
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
                return {
                    "readings": [], 
                    "model": data.get("model"), 
                    "serial_number": data.get("serialNumber"), 
                    "unit": data.get("unit")
                }
            
            # Validate readings format
            for i, reading in enumerate(data["readings"]):
                if not isinstance(reading, list) or len(reading) != 2:
                    raise APIError(f"Invalid reading format at index {i}: expected [timestamp, value]")
                
                if not isinstance(reading[0], (int, float)):
                    raise APIError(f"Invalid timestamp format at index {i}: expected number")
                
                if not isinstance(reading[1], (int, float)):
                    raise APIError(f"Invalid value format at index {i}: expected number")
            
            return data

        except (InvalidAuth, APIError):
            # Re-raise our custom exceptions
            raise
        except Exception as err:
            raise APIError(f"Unexpected error during API request: {err}") from err

    async def async_get_latest_reading(self) -> dict[str, Any]:
        """Get the latest water meter reading."""
        data = await self.async_get_readings()
        
        if not data or "readings" not in data or not data["readings"]:
            # Return None values instead of raising error for better UX
            return {
                "model": data.get("model") if data else None,
                "serial_number": data.get("serialNumber") if data else None,
                "unit": data.get("unit") if data else None,
                "timestamp": None,
                "value": None,
            }

        # Find the most recent reading
        latest_reading = max(data["readings"], key=lambda x: x[0])
        
        # Validate the reading data
        if not isinstance(latest_reading[0], (int, float)) or not isinstance(latest_reading[1], (int, float)):
            raise APIError("Invalid reading format in latest reading")
        
        return {
            "model": data.get("model"),
            "serial_number": data.get("serialNumber"),
            "unit": data.get("unit"),
            "timestamp": int(latest_reading[0]),
            "value": float(latest_reading[1]),
        }

    async def async_get_latest_reading_optimized(self) -> dict[str, Any]:
        """Get only the latest reading without fetching all data (if API supports it)."""
        # Try to get just the latest reading first
        try:
            # For now, use existing method but add caching logic
            # In future, this could call a specific endpoint for latest reading only
            data = await self.async_get_readings()
            
            if not data or "readings" not in data or not data["readings"]:
                return {
                    "model": data.get("model") if data else None,
                    "serial_number": data.get("serialNumber") if data else None,
                    "unit": data.get("unit") if data else None,
                    "timestamp": None,
                    "value": None,
                }

            # Find the most recent reading
            latest_reading = max(data["readings"], key=lambda x: x[0])
            
            # Validate the reading data
            if not isinstance(latest_reading[0], (int, float)) or not isinstance(latest_reading[1], (int, float)):
                raise APIError("Invalid reading format in latest reading")
            
            return {
                "model": data.get("model"),
                "serial_number": data.get("serialNumber"),
                "unit": data.get("unit"),
                "timestamp": int(latest_reading[0]),
                "value": float(latest_reading[1]),
            }
        except (InvalidAuth, APIError):
            raise
        except Exception as err:
            raise APIError(f"Unexpected error getting latest reading: {err}") from err

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
            # Validate reading format
            if not isinstance(reading, list) or len(reading) != 2:
                _LOGGER.warning("Skipping invalid reading format: %s", reading)
                continue
            
            if not isinstance(reading[0], (int, float)) or not isinstance(reading[1], (int, float)):
                _LOGGER.warning("Skipping reading with invalid types: %s", reading)
                continue
            
            readings.append({
                "model": data.get("model"),
                "serial_number": data.get("serialNumber"),  # Consistent naming
                "unit": data.get("unit"),
                "timestamp": int(reading[0]),  # Ensure integer timestamp
                "value": float(reading[1]),    # Ensure float value
            })
        
        # Sort by timestamp (oldest first)
        readings.sort(key=lambda x: x["timestamp"])
        return readings

    async def async_get_readings_since(
        self, since_timestamp: int
    ) -> list[dict[str, Any]]:
        """Get all readings since a specific timestamp."""
        # Calculate start date from timestamp with timezone awareness
        start_date = datetime.fromtimestamp(since_timestamp, tz=timezone.utc)
        
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
            
            # Validate reading data
            if not all(key in prev_reading for key in ["timestamp", "value"]):
                _LOGGER.warning("Skipping invalid previous reading: %s", prev_reading)
                continue
            
            if not all(key in curr_reading for key in ["timestamp", "value"]):
                _LOGGER.warning("Skipping invalid current reading: %s", curr_reading)
                continue
            
            # Ensure numeric values
            try:
                prev_value = float(prev_reading["value"])
                curr_value = float(curr_reading["value"])
                prev_timestamp = int(prev_reading["timestamp"])
                curr_timestamp = int(curr_reading["timestamp"])
            except (ValueError, TypeError) as err:
                _LOGGER.warning("Skipping reading with invalid numeric values: %s", err)
                continue
            
            # Calculate usage (difference in values)
            usage = curr_value - prev_value
            
            # Calculate time difference in hours
            time_diff = (curr_timestamp - prev_timestamp) / 3600
            
            # Skip if time difference is invalid
            if time_diff <= 0:
                _LOGGER.warning("Skipping readings with invalid time difference: %s", time_diff)
                continue
            
            usage_data.append({
                "start_timestamp": prev_timestamp,
                "end_timestamp": curr_timestamp,
                "start_value": prev_value,
                "end_value": curr_value,
                "usage": max(0, usage),  # Ensure non-negative usage
                "duration_hours": time_diff,
                "unit": curr_reading.get("unit", ""),
            })
        
        return usage_data

    async def async_test_connection(self) -> bool:
        """Test if the API connection is working."""
        try:
            await self.async_get_readings()
            return True
        except InvalidAuth:
            _LOGGER.warning("Authentication failed during connection test")
            return False
        except APIError as err:
            _LOGGER.warning("API error during connection test: %s", err)
            return False
        except Exception as err:
            _LOGGER.warning("Unexpected error during connection test: %s", err)
            return False

    async def async_get_all_historical_readings(self) -> list[dict[str, Any]]:
        """Get all available historical readings by iterating backwards until no data is found."""
        all_readings = []
        current_date = datetime.now(timezone.utc)
        batch_size_days = 30  # Fetch data in 30-day batches
        
        _LOGGER.info("Starting to fetch all available historical data")
        
        while True:
            # Calculate the date range for this batch
            start_date = current_date - timedelta(days=batch_size_days)
            
            try:
                # Get readings for this date range
                batch_readings = await self.async_get_readings_range(start_date, current_date)
                
                if not batch_readings:
                    # No more data available, stop fetching
                    _LOGGER.info("No more historical data available before %s", start_date.strftime("%Y-%m-%d"))
                    break
                
                # Add to our collection (avoiding duplicates)
                existing_timestamps = {r["timestamp"] for r in all_readings}
                new_readings = [r for r in batch_readings if r["timestamp"] not in existing_timestamps]
                all_readings.extend(new_readings)
                
                _LOGGER.info("Fetched %d readings for period %s to %s (total: %d)", 
                           len(batch_readings), start_date.strftime("%Y-%m-%d"), 
                           current_date.strftime("%Y-%m-%d"), len(all_readings))
                
                # Move to the next batch (further back in time)
                current_date = start_date
                
            except APIError as err:
                _LOGGER.warning("API error while fetching historical data for %s: %s", 
                               start_date.strftime("%Y-%m-%d"), err)
                break
            except Exception as err:
                _LOGGER.error("Unexpected error while fetching historical data: %s", err)
                break
        
        # Sort by timestamp (oldest first)
        all_readings.sort(key=lambda x: x["timestamp"])
        
        _LOGGER.info("Completed fetching all historical data: %d total readings", len(all_readings))
        return all_readings


class APIError(Exception):
    """Exception raised when API returns an error."""


class InvalidAuth(Exception):
    """Exception raised when authentication fails."""