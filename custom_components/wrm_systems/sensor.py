"""Sensor platform for WRM-Systems integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WRMSystemsDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WRM-Systems sensors from a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    sensors = [
        WRMSystemsWaterMeterSensor(coordinator, config_entry),
        WRMSystemsHourlyUsageSensor(coordinator, config_entry),
        WRMSystemsDailyUsageSensor(coordinator, config_entry),
        WRMSystemsWeeklyUsageSensor(coordinator, config_entry),
        WRMSystemsMonthlyUsageSensor(coordinator, config_entry),
    ]

    async_add_entities(sensors)


class WRMSystemsWaterMeterSensor(CoordinatorEntity, SensorEntity):
    """Representation of a WRM-Systems water meter sensor."""

    def __init__(
        self,
        coordinator: WRMSystemsDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = "Water Meter Reading"
        self._attr_unique_id = f"{config_entry.entry_id}_water_meter"
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_state_class = SensorStateClass.MEASUREMENT_INCREASING
        self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
        self._attr_suggested_display_precision = 3

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if self.coordinator.data is None:
            return False
        
        # Check if data is stale (older than 48 hours to account for API delay)
        timestamp = self.coordinator.data.get("timestamp")
        if timestamp is None:
            return False
        
        data_age = datetime.now().timestamp() - timestamp
        return data_age <= 48 * 3600  # 48 hours in seconds
    
    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if self.coordinator.data is None or not self.available:
            return None
        return self.coordinator.data.get("value")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if self.coordinator.data is None:
            return {}
        
        attributes = {
            "model": self.coordinator.data.get("model"),
            "serial_number": self.coordinator.data.get("serial_number"),
            "unit": self.coordinator.data.get("unit"),
            "last_reading": self.coordinator.data.get("timestamp"),
        }
        
        # Add data freshness information
        usage_data = self.coordinator.data.get("usage_data", {})
        if "data_age_hours" in usage_data:
            attributes["data_age_hours"] = round(usage_data["data_age_hours"], 1)
            
        return attributes

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": "WRM-Systems Water Meter",
            "manufacturer": "WRM-Systems",
            "model": self.coordinator.data.get("model") if self.coordinator.data else None,
            "serial_number": self.coordinator.data.get("serial_number") if self.coordinator.data else None,
        }


class WRMSystemsUsageBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for usage sensors with common functionality."""

    def __init__(
        self,
        coordinator: WRMSystemsDataUpdateCoordinator,
        config_entry: ConfigEntry,
        sensor_name: str,
        unique_id_suffix: str,
        usage_key: str,
    ) -> None:
        """Initialize the usage sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._usage_key = usage_key
        self._attr_name = sensor_name
        self._attr_unique_id = f"{config_entry.entry_id}_{unique_id_suffix}"
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
        self._attr_suggested_display_precision = 3

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if self.coordinator.data is None:
            return False
        
        # Check if data is stale (older than 48 hours to account for API delay)
        timestamp = self.coordinator.data.get("timestamp")
        if timestamp is None:
            return False
        
        data_age = datetime.now().timestamp() - timestamp
        return data_age <= 48 * 3600  # 48 hours in seconds
    
    @property
    def native_value(self) -> float | None:
        """Return the usage value."""
        if self.coordinator.data is None or not self.available:
            return None

        usage_data = self.coordinator.data.get("usage_data")
        if usage_data is None:
            return None
        
        return usage_data.get(self._usage_key, 0.0)

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": "WRM-Systems Water Meter",
            "manufacturer": "WRM-Systems",
            "model": self.coordinator.data.get("model") if self.coordinator.data else None,
            "serial_number": self.coordinator.data.get("serial_number") if self.coordinator.data else None,
        }


class WRMSystemsMonthlyUsageSensor(WRMSystemsUsageBaseSensor):
    """Representation of monthly water usage sensor."""

    def __init__(
        self,
        coordinator: WRMSystemsDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            config_entry,
            "Monthly Water Usage",
            "monthly_usage",
            "monthly_usage"
        )


class WRMSystemsHourlyUsageSensor(WRMSystemsUsageBaseSensor):
    """Representation of hourly water usage sensor."""

    def __init__(
        self,
        coordinator: WRMSystemsDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            config_entry,
            "Hourly Water Usage",
            "hourly_usage",
            "hourly_usage"
        )


class WRMSystemsDailyUsageSensor(WRMSystemsUsageBaseSensor):
    """Representation of daily water usage sensor."""

    def __init__(
        self,
        coordinator: WRMSystemsDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            config_entry,
            "Daily Water Usage",
            "daily_usage",
            "daily_usage"
        )


class WRMSystemsWeeklyUsageSensor(WRMSystemsUsageBaseSensor):
    """Representation of weekly water usage sensor."""

    def __init__(
        self,
        coordinator: WRMSystemsDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            config_entry,
            "Weekly Water Usage",
            "weekly_usage",
            "weekly_usage"
        )