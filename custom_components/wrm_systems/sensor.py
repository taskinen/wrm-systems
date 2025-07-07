"""Sensor platform for WRM-Systems integration."""
from __future__ import annotations

import logging
from datetime import datetime
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
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
        self._attr_suggested_display_precision = 3

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("value")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if self.coordinator.data is None:
            return {}
        
        return {
            "model": self.coordinator.data.get("model"),
            "serial_number": self.coordinator.data.get("serial_number"),
            "unit": self.coordinator.data.get("unit"),
            "last_reading": self.coordinator.data.get("timestamp"),
        }

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


class WRMSystemsMonthlyUsageSensor(CoordinatorEntity, SensorEntity):
    """Representation of monthly water usage sensor."""

    def __init__(
        self,
        coordinator: WRMSystemsDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = "Monthly Water Usage"
        self._attr_unique_id = f"{config_entry.entry_id}_monthly_usage"
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
        self._attr_suggested_display_precision = 3

    @property
    def native_value(self) -> float | None:
        """Return the monthly usage."""
        if self.coordinator.data is None:
            return None

        usage_data = self.coordinator.data.get("usage_data")
        if usage_data is None:
            return None
        
        return usage_data.get("monthly_usage", 0.0)

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


class WRMSystemsHourlyUsageSensor(CoordinatorEntity, SensorEntity):
    """Representation of hourly water usage sensor."""

    def __init__(
        self,
        coordinator: WRMSystemsDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = "Hourly Water Usage"
        self._attr_unique_id = f"{config_entry.entry_id}_hourly_usage"
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
        self._attr_suggested_display_precision = 3

    @property
    def native_value(self) -> float | None:
        """Return the hourly usage."""
        if self.coordinator.data is None:
            return None

        usage_data = self.coordinator.data.get("usage_data")
        if usage_data is None:
            return None
        
        return usage_data.get("hourly_usage", 0.0)

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


class WRMSystemsDailyUsageSensor(CoordinatorEntity, SensorEntity):
    """Representation of daily water usage sensor."""

    def __init__(
        self,
        coordinator: WRMSystemsDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = "Daily Water Usage"
        self._attr_unique_id = f"{config_entry.entry_id}_daily_usage"
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
        self._attr_suggested_display_precision = 3

    @property
    def native_value(self) -> float | None:
        """Return the daily usage."""
        if self.coordinator.data is None:
            return None

        usage_data = self.coordinator.data.get("usage_data")
        if usage_data is None:
            return None
        
        return usage_data.get("daily_usage", 0.0)

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


class WRMSystemsWeeklyUsageSensor(CoordinatorEntity, SensorEntity):
    """Representation of weekly water usage sensor."""

    def __init__(
        self,
        coordinator: WRMSystemsDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = "Weekly Water Usage"
        self._attr_unique_id = f"{config_entry.entry_id}_weekly_usage"
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
        self._attr_suggested_display_precision = 3

    @property
    def native_value(self) -> float | None:
        """Return the weekly usage."""
        if self.coordinator.data is None:
            return None

        usage_data = self.coordinator.data.get("usage_data")
        if usage_data is None:
            return None
        
        return usage_data.get("weekly_usage", 0.0)

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