"""Constants for the WRM-Systems integration."""
DOMAIN = "wrm_systems"

# Configuration
CONF_TOKEN = "token"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_MAX_DATA_AGE_HOURS = "max_data_age_hours"
CONF_HISTORICAL_DAYS = "historical_days"

# Default values
DEFAULT_SCAN_INTERVAL = 3600  # 1 hour in seconds
MIN_SCAN_INTERVAL = 300       # 5 minutes minimum
MAX_SCAN_INTERVAL = 86400     # 24 hours maximum
API_BASE_URL = "https://wmd.wrm-systems.fi/api/watermeter"

# Historical data configuration
DEFAULT_HISTORICAL_DAYS = -1  # -1 means fetch all available data
MIN_HISTORICAL_DAYS = 1
MAX_HISTORICAL_DAYS = 3650    # 10 years maximum

# Data retention and staleness
MAX_DATA_AGE_HOURS = 48
DEFAULT_MAX_DATA_AGE_HOURS = 48
MIN_MAX_DATA_AGE_HOURS = 6
MAX_MAX_DATA_AGE_HOURS = 168  # 7 days

# Legacy constants (kept for backward compatibility but not used for storage limits)
HISTORICAL_DATA_DAYS = 30
BACKFILL_DAYS = 7

# Validation constants (removed storage limits)
MIN_BACKFILL_DAYS = 1
MAX_BACKFILL_DAYS = 30
MIN_HISTORICAL_READINGS = 10
# MAX_HISTORICAL_READINGS removed - unlimited storage
MIN_HISTORICAL_DATA_DAYS = 1
MAX_HISTORICAL_DATA_DAYS = 90

# API request configuration
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2

# Validation functions
def validate_scan_interval(interval: int) -> bool:
    """Validate scan interval is within acceptable range."""
    return isinstance(interval, int) and MIN_SCAN_INTERVAL <= interval <= MAX_SCAN_INTERVAL

def validate_max_data_age_hours(hours: int) -> bool:
    """Validate max data age hours is within acceptable range."""
    return isinstance(hours, int) and MIN_MAX_DATA_AGE_HOURS <= hours <= MAX_MAX_DATA_AGE_HOURS

def validate_historical_days(days: int) -> bool:
    """Validate historical data days is within acceptable range."""
    if days == -1:  # -1 means fetch all available data
        return True
    return isinstance(days, int) and MIN_HISTORICAL_DAYS <= days <= MAX_HISTORICAL_DAYS