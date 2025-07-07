# WRM-Systems Water Meter Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Home Assistant HACS integration for reading water meter usage data from WRM-Systems cloud API.

## Features

- **Real-time water meter readings**: Get cumulative water consumption data from your WRM-Systems water meter
- **Hourly usage tracking**: Monitor water usage on an hourly basis
- **Daily usage tracking**: Track daily water consumption patterns
- **Historical data**: Access up to 30 days of historical readings
- **Easy setup**: Simple configuration flow with API token authentication

## Installation

### Via HACS (Recommended)

1. Add this repository to HACS as a custom repository
2. Search for "WRM-Systems" in HACS
3. Install the integration
4. Restart Home Assistant

### Manual Installation

1. Download the `wrm_systems` folder from this repository
2. Place it in your `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "WRM-Systems"
4. Enter your WRM-Systems API authentication token

### Getting Your API Token

Contact WRM-Systems to obtain your API authentication token for accessing the water meter data.

## Sensors

The integration provides five sensors:

- **Water Meter Reading**: Current cumulative water consumption (m³)
- **Hourly Water Usage**: Water consumption in the current hour (m³)
- **Daily Water Usage**: Water consumption today (m³)
- **Weekly Water Usage**: Water consumption this week (m³)
- **Monthly Water Usage**: Water consumption this month (m³)

## API Information

The integration fetches data from the WRM-Systems API:
- **Endpoint**: `https://wmd.wrm-systems.fi/api/watermeter`
- **Authentication**: Bearer token in HTTP header
- **Update interval**: 1 hour (configurable)
- **Historical data**: Up to 30 days per request

## Data Format

The API returns hourly readings in cubic meters (m³). Readings are cumulative values showing total consumption since meter installation.

## Troubleshooting

- **Authentication errors**: Verify your API token is correct
- **No data**: Check if your water meter is properly connected to the WRM-Systems network
- **Old data**: Readings may take 6-24 hours to appear in the API

## Support

For issues with this integration, please [open an issue on GitHub](https://github.com/taskinen/wrm-systems/issues).

For WRM-Systems API or hardware issues, contact WRM-Systems directly.

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Author

- **Timo Taskinen** - timo.taskinen@iki.fi
