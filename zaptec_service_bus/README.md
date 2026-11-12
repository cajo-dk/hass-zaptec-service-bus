# Zaptec Service Bus Monitor Add-on

Home Assistant add-on that listens to Zaptec Azure Service Bus messages and publishes charger state + attributes over MQTT.

## Configuration

Set values in the add-on Configuration tab:

- `azure_service_bus_connection_string`
- `azure_service_bus_topic_name`
- `azure_service_bus_subscription_name`
- `azure_service_bus_max_wait_time`
- `azure_service_bus_receive_mode`
- `azure_service_bus_transport`
- `mqtt_host`
- `mqtt_port`
- `mqtt_username`
- `mqtt_password`
- `mqtt_keepalive`
- `mqtt_client_id`
- `mqtt_base_topic`
- `mqtt_discovery_prefix`
- `mqtt_discovery_enabled`
- `mqtt_retain`
- `log_level` (`ERROR`, `INFO`, `DEBUG`)

Only `DEBUG` logs message payloads.

## Dependency and schedule observation update

Version 0.2.1 updates the stable Python dependency pins and exposes raw Zaptec
schedule observations as `time_zone` (761), `time_schedule` (762), and
`next_schedule_event` (763) attributes on the existing charge status sensor.
An empty schedule observation clears the cached value.

For Monta-managed plans, enable `monta_enabled` and configure the Monta Public
API client credentials, Hub Cookie, and charge-point ID. The app reads the Hub
schedule over HTTP every 30 seconds and publishes five MQTT-discovered sensors
for connection state, SoC, calculated start, estimated completion, and latest
completion. Estimated completion uses the configured battery capacity and the
lower of vehicle charging power and Monta's planner power limit.

The Hub Cookie expires with the session and must then be refreshed in the app
configuration. See the root README for configuration, verified entity IDs, and
the distinction between estimated completion and the configured deadline.

Schedule dates display in Copenhagen time as `dd/mm/yyyy hh.mm` (24 hours).
The original ISO timestamps remain available in the sensor attributes.
