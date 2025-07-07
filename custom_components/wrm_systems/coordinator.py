"""DataUpdateCoordinator for WRM-Systems integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.storage import Store

from .api import WRMSystemsAPIClient, APIError, InvalidAuth
from .const import (
    DEFAULT_SCAN_INTERVAL, 
    DOMAIN, 
    MAX_DATA_AGE_HOURS,
    HISTORICAL_DATA_DAYS,
    BACKFILL_DAYS,
    MAX_HISTORICAL_READINGS,
    MIN_BACKFILL_DAYS,
    MAX_BACKFILL_DAYS,
    MIN_HISTORICAL_READINGS,
    CONF_SCAN_INTERVAL,
)

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
        self._storage_lock = asyncio.Lock()

        # Get scan interval from config, with fallback to default
        scan_interval = config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    def _validate_reading(self, reading: dict[str, Any]) -> bool:
        """Validate a single reading has required fields and valid data."""
        try:
            required_fields = ["timestamp", "value"]
            if not all(field in reading for field in required_fields):
                return False
            
            # Validate timestamp is reasonable (not too old or in future)
            timestamp = reading["timestamp"]
            if not isinstance(timestamp, (int, float)):
                return False
                
            current_time = datetime.now(timezone.utc).timestamp()
            # Allow readings up to 90 days old, reject future readings
            if timestamp < (current_time - 90 * 24 * 3600) or timestamp > current_time:
                return False
            
            # Validate value is a reasonable number (positive, not extreme)
            value = reading["value"]
            if not isinstance(value, (int, float)) or value < 0 or value > 1e9:
                return False
                
            return True
        except (KeyError, TypeError, ValueError):
            return False

    def _safe_get_timestamp(self, data: dict[str, Any] | None) -> int | None:
        """Safely extract timestamp from data with validation."""
        try:
            if not data:
                return None
            timestamp = data.get("timestamp")
            if timestamp is None:
                return None
            if isinstance(timestamp, (int, float)) and timestamp > 0:
                return int(timestamp)
            return None
        except (TypeError, ValueError):
            return None

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""
        try:
            # Load stored data on first run (protected by lock)
            if not self._historical_data:
                async with self._storage_lock:
                    # Double-check pattern: verify again inside the lock
                    if not self._historical_data:
                        await self._load_historical_data()
            
            # Get new readings since last update
            new_readings = await self._fetch_new_readings()
            
            # Update historical data with new readings
            if new_readings:
                await self._update_historical_data(new_readings)
            
            # Periodically clean up storage (every 10th update)
            if hasattr(self, '_update_count'):
                self._update_count += 1
                # Reset counter to prevent overflow on long-running systems
                if self._update_count > 1000:
                    self._update_count = 1
            else:
                self._update_count = 1
                
            if self._update_count % 10 == 0:
                await self._periodic_storage_cleanup()
            
            # Get the latest reading for current sensors
            latest_data = await self.api.async_get_latest_reading()
            
            # Handle case where no data is available
            if latest_data.get("timestamp") is None or latest_data.get("value") is None:
                _LOGGER.warning("No valid readings available from API")
                # Return minimal data structure to prevent sensor errors
                latest_data = {
                    "model": latest_data.get("model"),
                    "serial_number": latest_data.get("serial_number"),
                    "unit": latest_data.get("unit"),
                    "timestamp": None,
                    "value": None,
                    "usage_data": {
                        "hourly_usage": 0.0,
                        "daily_usage": 0.0,
                        "weekly_usage": 0.0,
                        "monthly_usage": 0.0,
                        "data_age_hours": 0.0,
                    }
                }
            else:
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
            if stored_data and isinstance(stored_data, dict):
                # Validate stored data structure
                if "readings" in stored_data and isinstance(stored_data["readings"], list):
                    self._historical_data = stored_data
                    self._last_reading_timestamp = stored_data.get("last_reading_timestamp")
                    _LOGGER.debug("Loaded historical data with %d readings", 
                                 len(stored_data.get("readings", [])))
                else:
                    _LOGGER.warning("Invalid stored data structure, resetting")
                    self._historical_data = {"readings": [], "last_reading_timestamp": None}
            else:
                self._historical_data = {"readings": [], "last_reading_timestamp": None}
                _LOGGER.debug("No valid historical data found, starting fresh")
        except Exception as err:
            _LOGGER.error("Failed to load historical data: %s", err)
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
                # First run - get readings from last N days
                start_date = datetime.now(timezone.utc) - timedelta(days=BACKFILL_DAYS)
                new_readings = await self.api.async_get_readings_range(start_date)
                _LOGGER.debug("Initial fetch found %d readings from last %d days", 
                             len(new_readings), BACKFILL_DAYS)
            
            return new_readings
        except APIError as err:
            _LOGGER.warning("Failed to fetch new readings: %s", err)
            return []
    
    async def _update_historical_data(self, new_readings: list[dict[str, Any]]) -> None:
        """Update historical data with new readings."""
        if not new_readings:
            return
        
        async with self._storage_lock:
            existing_readings = self._historical_data.get("readings", [])
            
            # More efficient: use set for O(1) lookup of existing timestamps
            existing_timestamps = {r["timestamp"] for r in existing_readings}
            
            # Only add truly new readings that pass validation
            new_unique_readings = [
                reading for reading in new_readings 
                if reading["timestamp"] not in existing_timestamps and self._validate_reading(reading)
            ]
            
            if len(new_readings) != len(new_unique_readings):
                _LOGGER.warning("Filtered out %d invalid readings", len(new_readings) - len(new_unique_readings))
            
            # Combine and sort only if we have new readings
            if new_unique_readings:
                combined_readings = existing_readings + new_unique_readings
                combined_readings.sort(key=lambda x: x["timestamp"])
                
                # Apply time-based filter
                cutoff_timestamp = int((datetime.now(timezone.utc) - timedelta(days=HISTORICAL_DATA_DAYS)).timestamp())
                recent_readings = [
                    r for r in combined_readings 
                    if r["timestamp"] >= cutoff_timestamp
                ]
                
                # Apply maximum limit
                if len(recent_readings) > MAX_HISTORICAL_READINGS:
                    recent_readings = recent_readings[-MAX_HISTORICAL_READINGS:]
                    _LOGGER.info("Trimmed historical data to %d readings", MAX_HISTORICAL_READINGS)
                
                # Update data
                self._historical_data["readings"] = recent_readings
                if recent_readings:
                    self._last_reading_timestamp = recent_readings[-1]["timestamp"]
                    self._historical_data["last_reading_timestamp"] = self._last_reading_timestamp
                
                await self.store.async_save(self._historical_data)
                _LOGGER.debug("Updated historical data with %d new readings", len(new_unique_readings))
            else:
                _LOGGER.debug("No new readings to add")
            
            # Ensure minimum readings for meaningful calculations
            current_readings = self._historical_data.get("readings", [])
            if len(current_readings) > 0 and len(current_readings) < MIN_HISTORICAL_READINGS:
                _LOGGER.debug("Historical data has only %d readings (minimum recommended: %d)", 
                             len(current_readings), MIN_HISTORICAL_READINGS)
    
    def _calculate_usage_metrics(self) -> dict[str, Any]:
        """Calculate usage metrics from historical data."""
        readings = self._historical_data.get("readings", [])
        if len(readings) < 2:
            return {"hourly_usage": 0, "daily_usage": 0, "weekly_usage": 0}
        
        # Use Home Assistant's timezone for user-centric calculations
        local_tz = self.hass.config.time_zone
        current_time_utc = datetime.now(timezone.utc)
        current_time_local = current_time_utc.astimezone(local_tz)
        current_timestamp = int(current_time_utc.timestamp())
        
        # Get latest reading
        latest_reading = max(readings, key=lambda x: x["timestamp"])
        
        # Calculate hourly usage (average based on recent readings)
        # Since API has 6-24 hour delay, we can't get true "last hour" data
        # Instead, calculate average hourly usage from recent readings
        hourly_usage = self._calculate_average_hourly_usage(readings)
        
        # Calculate daily usage (since start of day in local time)
        start_of_day_local = current_time_local.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_day = int(start_of_day_local.timestamp())
        daily_readings = [r for r in readings if r["timestamp"] >= start_of_day]
        daily_usage = self._calculate_usage_for_period(daily_readings)
        
        # Calculate weekly usage (last 7 days)
        week_ago = current_timestamp - (7 * 24 * 3600)
        weekly_readings = [r for r in readings if r["timestamp"] >= week_ago]
        weekly_usage = self._calculate_usage_for_period(weekly_readings)
        
        # Calculate monthly usage (since start of month in local time)
        start_of_month_local = current_time_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_of_month = int(start_of_month_local.timestamp())
        monthly_readings = [r for r in readings if r["timestamp"] >= start_of_month]
        monthly_usage = self._calculate_usage_for_period(monthly_readings)
        
        # Calculate data age safely
        latest_timestamp = latest_reading.get("timestamp")
        data_age_hours = 0.0
        if latest_timestamp:
            data_age_hours = (current_timestamp - latest_timestamp) / 3600
        
        return {
            "hourly_usage": hourly_usage,
            "daily_usage": daily_usage,
            "weekly_usage": weekly_usage,
            "monthly_usage": monthly_usage,
            "latest_reading": latest_reading,
            "data_age_hours": data_age_hours,
        }
    
    def _calculate_usage_for_period(self, readings: list[dict[str, Any]]) -> float:
        """Calculate usage for a specific period."""
        if not readings or len(readings) < 2:
            return 0.0
        
        try:
            # Validate and filter readings
            valid_readings = []
            for reading in readings:
                if not isinstance(reading, dict):
                    continue
                timestamp = reading.get("timestamp")
                value = reading.get("value")
                if timestamp is not None and value is not None:
                    try:
                        # More robust type conversion with string handling
                        if isinstance(timestamp, str):
                            timestamp = int(float(timestamp))
                        elif isinstance(timestamp, (int, float)):
                            timestamp = int(timestamp)
                        else:
                            continue
                            
                        if isinstance(value, str):
                            value = float(value)
                        elif isinstance(value, (int, float)):
                            value = float(value)
                        else:
                            continue
                            
                        # Validate ranges
                        if timestamp > 0 and not (value < 0 or value > 999999):
                            valid_readings.append({"timestamp": timestamp, "value": value})
                    except (ValueError, TypeError, OverflowError):
                        continue
            
            if len(valid_readings) < 2:
                return 0.0
            
            # Sort by timestamp
            valid_readings.sort(key=lambda x: x["timestamp"])
            
            # Calculate usage as difference between first and last reading
            first_value = valid_readings[0]["value"]
            last_value = valid_readings[-1]["value"]
            
            usage = last_value - first_value
            return max(0, usage)  # Ensure non-negative usage
            
        except Exception as err:
            _LOGGER.warning("Error calculating usage for period: %s", err)
            return 0.0
    
    def _calculate_average_hourly_usage(self, readings: list[dict[str, Any]]) -> float:
        """Calculate average hourly usage from recent readings (accounting for API delay)."""
        if not readings or len(readings) < 2:
            return 0.0
        
        try:
            # Validate and filter readings
            valid_readings = []
            for reading in readings:
                if not isinstance(reading, dict):
                    continue
                timestamp = reading.get("timestamp")
                value = reading.get("value")
                if timestamp is not None and value is not None:
                    try:
                        # More robust type conversion with string handling
                        if isinstance(timestamp, str):
                            timestamp = int(float(timestamp))
                        elif isinstance(timestamp, (int, float)):
                            timestamp = int(timestamp)
                        else:
                            continue
                            
                        if isinstance(value, str):
                            value = float(value)
                        elif isinstance(value, (int, float)):
                            value = float(value)
                        else:
                            continue
                            
                        # Validate ranges
                        if timestamp > 0 and not (value < 0 or value > 999999):
                            valid_readings.append({"timestamp": timestamp, "value": value})
                    except (ValueError, TypeError, OverflowError):
                        continue
            
            if len(valid_readings) < 2:
                return 0.0
            
            # Sort by timestamp
            valid_readings.sort(key=lambda x: x["timestamp"])
            
            # Get the most recent MAX_DATA_AGE_HOURS hours of readings
            # Fix: Calculate once for efficiency
            current_timestamp = datetime.now(timezone.utc).timestamp()
            cutoff_timestamp = current_timestamp - (MAX_DATA_AGE_HOURS * 3600)
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
            
        except Exception as err:
            _LOGGER.warning("Error calculating average hourly usage: %s", err)
            return 0.0
    
    async def async_get_usage_history(self, days: int = 7) -> list[dict[str, Any]]:
        """Get usage history for the specified number of days."""
        readings = self._historical_data.get("readings", [])
        
        # Filter readings for the specified period
        cutoff_timestamp = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
        period_readings = [r for r in readings if r["timestamp"] >= cutoff_timestamp]
        
        # Calculate usage between consecutive readings
        return self.api.calculate_usage_from_readings(period_readings)
    
    async def async_backfill_data(self, days: int = 7) -> None:
        """Backfill historical data for late-arriving readings."""
        # Validate input parameters
        if not isinstance(days, int) or days < MIN_BACKFILL_DAYS or days > MAX_BACKFILL_DAYS:
            raise ValueError(f"Days must be an integer between {MIN_BACKFILL_DAYS} and {MAX_BACKFILL_DAYS}")
        
        _LOGGER.info("Starting backfill operation for last %d days", days)
        
        try:
            # Get date range for backfill
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days)
            
            # Fetch all readings for the period
            backfill_readings = await self.api.async_get_readings_range(start_date, end_date)
            
            if not backfill_readings:
                _LOGGER.info("No readings found for backfill period")
                return
            
            # Protect the entire backfill operation with lock
            async with self._storage_lock:
                # Load existing data
                if not self._historical_data:
                    await self._load_historical_data()
                
                # Merge with existing readings
                existing_readings = self._historical_data.get("readings", [])
                all_readings = existing_readings + backfill_readings
                
                # Remove duplicates and sort
                unique_readings = {r["timestamp"]: r for r in all_readings}
                sorted_readings = sorted(unique_readings.values(), key=lambda x: x["timestamp"])
                
                # Keep only last N days
                cutoff_timestamp = int((datetime.now(timezone.utc) - timedelta(days=HISTORICAL_DATA_DAYS)).timestamp())
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
            # Protect the entire force refresh operation with lock
            async with self._storage_lock:
                # Clear existing data
                self._historical_data = {"readings": [], "last_reading_timestamp": None}
                self._last_reading_timestamp = None
                
                # Backfill last N days of data (this will acquire the lock again but that's ok)
                # Note: We need to release the lock temporarily for backfill
                pass
            
            # Now do backfill (which has its own locking)
            await self.async_backfill_data(BACKFILL_DAYS)
            
            # Trigger coordinator update
            await self.async_refresh()
            
            _LOGGER.info("Force refresh completed")
            
        except Exception as err:
            _LOGGER.error("Force refresh failed: %s", err)
            raise
    
    async def _periodic_storage_cleanup(self) -> None:
        """Perform periodic cleanup of storage to prevent unbounded growth."""
        try:
            async with self._storage_lock:
                readings = self._historical_data.get("readings", [])
                
                # Only cleanup if we have too many readings
                if len(readings) <= MAX_HISTORICAL_READINGS:
                    return
                    
                # Calculate cleanup threshold (keep recent data, clean old data)
                cutoff_timestamp = int((datetime.now(timezone.utc) - timedelta(days=HISTORICAL_DATA_DAYS)).timestamp())
                
                # Filter readings and apply limits
                recent_readings = [r for r in readings if r["timestamp"] >= cutoff_timestamp]
                recent_readings.sort(key=lambda x: x["timestamp"])
                
                # Keep maximum number of readings
                if len(recent_readings) > MAX_HISTORICAL_READINGS:
                    recent_readings = recent_readings[-MAX_HISTORICAL_READINGS:]
                
                # Update if changed
                if len(recent_readings) != len(readings):
                    old_count = len(readings)
                    self._historical_data["readings"] = recent_readings
                    
                    if recent_readings:
                        self._last_reading_timestamp = recent_readings[-1]["timestamp"]
                        self._historical_data["last_reading_timestamp"] = self._last_reading_timestamp
                    
                    await self.store.async_save(self._historical_data)
                    _LOGGER.info("Storage cleanup: reduced from %d to %d readings", old_count, len(recent_readings))
                    
        except Exception as err:
            _LOGGER.error("Storage cleanup failed: %s", err)