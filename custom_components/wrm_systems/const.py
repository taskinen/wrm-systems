"""Constants for the WRM-Systems integration."""
DOMAIN = "wrm_systems"

# Configuration
CONF_TOKEN = "token"
CONF_SCAN_INTERVAL = "scan_interval"

# Default values
DEFAULT_SCAN_INTERVAL = 3600  # 1 hour in seconds
MIN_SCAN_INTERVAL = 300       # 5 minutes minimum
MAX_SCAN_INTERVAL = 86400     # 24 hours maximum
API_BASE_URL = "https://wmd.wrm-systems.fi/api/watermeter"

# Data retention and staleness
MAX_DATA_AGE_HOURS = 48
HISTORICAL_DATA_DAYS = 30
BACKFILL_DAYS = 7