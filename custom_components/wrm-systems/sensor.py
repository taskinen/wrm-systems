import os
import datetime
import logging
from homeassistant.helpers.entity import Entity
from homeassistant.const import DEVICE_CLASS_TIMESTAMP
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

def setup_platform(hass, config, add_entities, discovery_info=None):
    path = config.get("file_path", "/config/timestamp.txt")
    add_entities([TimestampSensor(path)], True)

class TimestampSensor(Entity):
    def __init__(self, path):
        self._path = path
        self._state = None

    @property
    def name(self):
        return "My Timestamp"

    @property
    def state(self):
        return self._state

    @property
    def device_class(self):
        return DEVICE_CLASS_TIMESTAMP

    def update(self):
        now = datetime.datetime.now().isoformat()
        _LOGGER.debug("Writing timestamp: %s", now)
        self._state = now
        with open(self._path, "w", encoding="utf-8") as f:
            f.write(now)
