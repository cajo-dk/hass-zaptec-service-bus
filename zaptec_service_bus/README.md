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
- `mqtt_retain`
