"""DataUpdateCoordinator for WRM-Systems integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.storage import Store

from .api import WRMSystemsAPIClient, APIError, InvalidAuth
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1


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
        
        # Initialize storage for historical data (unique per config entry)
        storage_key = f"wrm_systems_data_{config_entry.entry_id}"
        self.store = Store(hass, STORAGE_VERSION, storage_key)
        self._historical_data: dict[str, Any] = {}
        self._last_reading_timestamp: int | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""
        try:
            # Load stored data on first run
            if not self._historical_data:
                await self._load_historical_data()
            
            # Get new readings since last update
            new_readings = await self._fetch_new_readings()
            
            # Update historical data with new readings
            if new_readings:
                await self._update_historical_data(new_readings)
            
            # Get the latest reading for current sensors
            latest_data = await self.api.async_get_latest_reading()
            
            # Add calculated usage data
            latest_data["usage_data"] = self._calculate_usage_metrics()
            
            _LOGGER.debug("Successfully fetched data: %s", latest_data)
            return latest_data
            
        except InvalidAuth as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except APIError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
    
    async def _load_historical_data(self) -> None:
        """Load historical data from storage."""
        try:
            stored_data = await self.store.async_load()
            if stored_data:
                self._historical_data = stored_data
                self._last_reading_timestamp = stored_data.get("last_reading_timestamp")
                _LOGGER.debug("Loaded historical data with %d readings", 
                             len(stored_data.get("readings", [])))
            else:
                self._historical_data = {"readings": [], "last_reading_timestamp": None}
                _LOGGER.debug("No historical data found, starting fresh")
        except Exception as err:
            _LOGGER.warning("Failed to load historical data: %s", err)
            self._historical_data = {"readings": [], "last_reading_timestamp": None}
    
    async def _fetch_new_readings(self) -> list[dict[str, Any]]:
        """Fetch new readings since last update."""
        try:
            if self._last_reading_timestamp:
                # Get readings since last known timestamp
                new_readings = await self.api.async_get_readings_since(
                    self._last_reading_timestamp
                )
                _LOGGER.debug("Found %d new readings since last update", len(new_readings))
            else:
                # First run - get readings from last 7 days
                start_date = datetime.now() - timedelta(days=7)
                new_readings = await self.api.async_get_readings_range(start_date)
                _LOGGER.debug("Initial fetch found %d readings from last 7 days", len(new_readings))
            
            return new_readings
        except APIError as err:
            _LOGGER.warning("Failed to fetch new readings: %s", err)
            return []
    
    async def _update_historical_data(self, new_readings: list[dict[str, Any]]) -> None:
        """Update historical data with new readings."""
        if not new_readings:
            return
        
        # Add new readings to historical data
        existing_readings = self._historical_data.get("readings", [])
        all_readings = existing_readings + new_readings
        
        # Remove duplicates and sort by timestamp
        unique_readings = {r["timestamp"]: r for r in all_readings}
        sorted_readings = sorted(unique_readings.values(), key=lambda x: x["timestamp"])
        
        # Keep only last 30 days of data
        cutoff_timestamp = int((datetime.now() - timedelta(days=30)).timestamp())
        recent_readings = [r for r in sorted_readings if r["timestamp"] >= cutoff_timestamp]
        
        # Update historical data
        self._historical_data["readings"] = recent_readings
        self._last_reading_timestamp = max(r["timestamp"] for r in recent_readings)
        self._historical_data["last_reading_timestamp"] = self._last_reading_timestamp
        
        # Save to storage
        await self.store.async_save(self._historical_data)
        _LOGGER.debug("Updated historical data with %d readings", len(recent_readings))
    
    def _calculate_usage_metrics(self) -> dict[str, Any]:
        """Calculate usage metrics from historical data."""
        readings = self._historical_data.get("readings", [])
        if len(readings) < 2:
            return {"hourly_usage": 0, "daily_usage": 0, "weekly_usage": 0}
        
        current_time = datetime.now()
        current_timestamp = int(current_time.timestamp())
        
        # Get latest reading
        latest_reading = max(readings, key=lambda x: x["timestamp"])
        
        # Calculate hourly usage (average based on recent readings)
        # Since API has 6-24 hour delay, we can't get true "last hour" data
        # Instead, calculate average hourly usage from recent readings
        hourly_usage = self._calculate_average_hourly_usage(readings)
        
        # Calculate daily usage (since start of day)
        start_of_day = int(current_time.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        daily_readings = [r for r in readings if r["timestamp"] >= start_of_day]
        daily_usage = self._calculate_usage_for_period(daily_readings)
        
        # Calculate weekly usage (last 7 days)
        week_ago = current_timestamp - (7 * 24 * 3600)
        weekly_readings = [r for r in readings if r["timestamp"] >= week_ago]
        weekly_usage = self._calculate_usage_for_period(weekly_readings)
        
        # Calculate monthly usage (since start of month)
        start_of_month = int(current_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
        monthly_readings = [r for r in readings if r["timestamp"] >= start_of_month]
        monthly_usage = self._calculate_usage_for_period(monthly_readings)
        
        return {
            "hourly_usage": hourly_usage,
            "daily_usage": daily_usage,
            "weekly_usage": weekly_usage,
            "monthly_usage": monthly_usage,
            "latest_reading": latest_reading,
            "data_age_hours": (current_timestamp - latest_reading.get("timestamp", 0)) / 3600,
        }
    
    def _calculate_usage_for_period(self, readings: list[dict[str, Any]]) -> float:
        """Calculate usage for a specific period."""
        if not readings or len(readings) < 2:
            return 0.0
        
        try:
            # Sort by timestamp and validate data
            sorted_readings = sorted(readings, key=lambda x: x.get("timestamp", 0))
            
            # Filter out invalid readings
            valid_readings = [
                r for r in sorted_readings 
                if r.get("timestamp") and r.get("value") is not None
            ]
            
            if len(valid_readings) < 2:
                return 0.0
            
            # Calculate usage as difference between first and last reading
            first_reading = valid_readings[0]
            last_reading = valid_readings[-1]
            
            first_value = first_reading.get("value", 0)
            last_value = last_reading.get("value", 0)
            
            # Ensure values are numeric
            if not isinstance(first_value, (int, float)) or not isinstance(last_value, (int, float)):
                _LOGGER.warning("Invalid reading values: first=%s, last=%s", first_value, last_value)
                return 0.0
            
            usage = last_value - first_value
            return max(0, usage)  # Ensure non-negative usage
            
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.warning("Error calculating usage for period: %s", err)
            return 0.0
    
    def _calculate_average_hourly_usage(self, readings: list[dict[str, Any]]) -> float:
        """Calculate average hourly usage from recent readings (accounting for API delay)."""
        if not readings or len(readings) < 2:
            return 0.0
        
        try:
            # Sort by timestamp and validate data
            sorted_readings = sorted(readings, key=lambda x: x.get("timestamp", 0))
            
            # Filter out invalid readings
            valid_readings = [
                r for r in sorted_readings 
                if r.get("timestamp") and r.get("value") is not None
            ]
            
            if len(valid_readings) < 2:
                return 0.0
            
            # Get the most recent 24 hours of readings (accounting for delay)
            current_time = datetime.now().timestamp()
            # Look back 48 hours to account for potential delays
            cutoff_timestamp = current_time - (48 * 3600)
            recent_readings = [r for r in valid_readings if r["timestamp"] >= cutoff_timestamp]
            
            if len(recent_readings) < 2:
                # If no recent readings, use the last available readings
                recent_readings = valid_readings[-10:]  # Last 10 readings
            
            if len(recent_readings) < 2:
                return 0.0
            
            # Calculate total usage and time span
            first_reading = recent_readings[0]
            last_reading = recent_readings[-1]
            
            total_usage = last_reading["value"] - first_reading["value"]
            time_span_hours = (last_reading["timestamp"] - first_reading["timestamp"]) / 3600
            
            if time_span_hours <= 0:
                return 0.0
            
            # Calculate average hourly usage
            hourly_usage = total_usage / time_span_hours
            return max(0, hourly_usage)  # Ensure non-negative
            
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.warning("Error calculating average hourly usage: %s", err)
            return 0.0
    
    async def async_get_usage_history(self, days: int = 7) -> list[dict[str, Any]]:
        """Get usage history for the specified number of days."""
        readings = self._historical_data.get("readings", [])
        
        # Filter readings for the specified period
        cutoff_timestamp = int((datetime.now() - timedelta(days=days)).timestamp())
        period_readings = [r for r in readings if r["timestamp"] >= cutoff_timestamp]
        
        # Calculate usage between consecutive readings
        return self.api.calculate_usage_from_readings(period_readings)
    
    async def async_backfill_data(self, days: int = 7) -> None:
        """Backfill historical data for late-arriving readings."""
        _LOGGER.info("Starting backfill operation for last %d days", days)
        
        try:
            # Get date range for backfill
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Fetch all readings for the period
            backfill_readings = await self.api.async_get_readings_range(start_date, end_date)
            
            if not backfill_readings:
                _LOGGER.info("No readings found for backfill period")
                return
            
            # Load existing data
            await self._load_historical_data()
            
            # Merge with existing readings
            existing_readings = self._historical_data.get("readings", [])
            all_readings = existing_readings + backfill_readings
            
            # Remove duplicates and sort
            unique_readings = {r["timestamp"]: r for r in all_readings}
            sorted_readings = sorted(unique_readings.values(), key=lambda x: x["timestamp"])
            
            # Keep only last 30 days
            cutoff_timestamp = int((datetime.now() - timedelta(days=30)).timestamp())
            recent_readings = [r for r in sorted_readings if r["timestamp"] >= cutoff_timestamp]
            
            # Update historical data
            old_count = len(self._historical_data.get("readings", []))
            self._historical_data["readings"] = recent_readings
            
            if recent_readings:
                self._last_reading_timestamp = max(r["timestamp"] for r in recent_readings)
                self._historical_data["last_reading_timestamp"] = self._last_reading_timestamp
            
            # Save updated data
            await self.store.async_save(self._historical_data)
            
            new_count = len(recent_readings)
            _LOGGER.info("Backfill completed: %d readings (was %d, now %d)", 
                        new_count - old_count, old_count, new_count)
            
        except Exception as err:
            _LOGGER.error("Backfill operation failed: %s", err)
            raise
    
    async def async_force_refresh(self) -> None:
        """Force a complete refresh of data, including backfill."""
        _LOGGER.info("Force refresh requested")
        
        try:
            # Clear existing data
            self._historical_data = {"readings": [], "last_reading_timestamp": None}
            self._last_reading_timestamp = None
            
            # Backfill last 7 days of data
            await self.async_backfill_data(7)
            
            # Trigger coordinator update
            await self.async_refresh()
            
            _LOGGER.info("Force refresh completed")
            
        except Exception as err:
            _LOGGER.error("Force refresh failed: %s", err)
            raise