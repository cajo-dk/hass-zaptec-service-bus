# Zaptec Service Bus Home Assistant Add-on

Version: `0.0.6`

This repository provides a Home Assistant add-on that listens to Zaptec Azure Service Bus messages and publishes a Home Assistant MQTT sensor payload.

## Features

- Runs as a Home Assistant add-on (`zaptec_service_bus`).
- Reads all settings from the add-on Configuration tab.
- Subscribes to an Azure Service Bus topic/subscription over AMQP.
- Decodes Zaptec binary-wrapped JSON payloads.
- Maps `StateId 710` values to sensor `state`:
  - `1 -> disconnected`
  - `2 -> connected_requesting_charge`
  - `3 -> charging`
  - `5 -> connected_finished_idle`
- Publishes all other StateId values as sensor attributes.
- Sets numeric attributes to `0` until they are updated.
- Publishes MQTT discovery with `force_update: true`.

## Repository Layout

- [repository.yaml](c:/Users/AlexRasmussen/src/zaptec/repository.yaml): Home Assistant add-on repository metadata.
- [zaptec_service_bus/config.yaml](c:/Users/AlexRasmussen/src/zaptec/zaptec_service_bus/config.yaml): add-on manifest, options, schema, version.
- [zaptec_service_bus/Dockerfile](c:/Users/AlexRasmussen/src/zaptec/zaptec_service_bus/Dockerfile): add-on container build (base image provided by Supervisor).
- [zaptec_service_bus/run.sh](c:/Users/AlexRasmussen/src/zaptec/zaptec_service_bus/run.sh): maps add-on options to env vars and starts monitor.
- [zaptec_service_bus/zaptec_charge_monitor.py](c:/Users/AlexRasmussen/src/zaptec/zaptec_service_bus/zaptec_charge_monitor.py): monitor runtime in container.

## Install In Home Assistant

1. In Home Assistant, go to `Settings -> Add-ons -> Add-on Store`.
2. Click menu (`⋮`) -> `Repositories`.
3. Add this repository URL:
   - `https://github.com/cajo-dk/hass-zaptec-service-bus`
4. Open add-on `Zaptec Service Bus Monitor`.
5. Click `Install`.
6. Open the `Configuration` tab and fill values.
7. Start the add-on.

## Configuration (Configuration tab)

These map directly to runtime env vars consumed by the monitor:

- `azure_service_bus_connection_string` (required)
- `azure_service_bus_topic_name` (required)
- `azure_service_bus_subscription_name` (required)
- `azure_service_bus_max_wait_time` (default `5`)
- `azure_service_bus_receive_mode` (`peek_lock` or `receive_and_delete`)
- `azure_service_bus_transport` (`amqp`, `amqp_over_websocket`, `aqmp`)
- `mqtt_host` (required)
- `mqtt_port` (default `1883`)
- `mqtt_username` (optional)
- `mqtt_password` (optional)
- `mqtt_keepalive` (default `60`)
- `mqtt_client_id` (default `zaptec-charge-monitor`)
- `mqtt_base_topic` (default `zaptec`)
- `mqtt_discovery_prefix` (default `homeassistant`)
- `mqtt_retain` (default `true`)

Example values:

```yaml
azure_service_bus_connection_string: "Endpoint=sb://{Host}/;SharedAccessKeyName={UserName};SharedAccessKey={Password};EntityPath={Topic}"
azure_service_bus_topic_name: "{Topic}"
azure_service_bus_subscription_name: "{Subscription}"
azure_service_bus_max_wait_time: 5
azure_service_bus_receive_mode: "peek_lock"
azure_service_bus_transport: "amqp"
mqtt_host: "core-mosquitto"
mqtt_port: 1883
mqtt_username: ""
mqtt_password: ""
mqtt_keepalive: 60
mqtt_client_id: "zaptec-charge-monitor"
mqtt_base_topic: "zaptec"
mqtt_discovery_prefix: "homeassistant"
mqtt_retain: true
```

## Home Assistant Sensor Creation

No manual sensor YAML is required when MQTT discovery is enabled.

1. Ensure MQTT integration is configured in Home Assistant.
2. Start the add-on.
3. Add-on publishes discovery topic:
   - `homeassistant/sensor/zaptec_<charger_id>/config`
4. Home Assistant auto-creates sensor entity named like:
   - `Zaptec <device_id> Charge Status`

If you disabled discovery, manual fallback:

```yaml
mqtt:
  sensor:
    - name: "Zaptec Charge Status"
      unique_id: "zaptec_charge_status_manual"
      state_topic: "zaptec/chargers/<charger_id>/state"
      value_template: "{{ value_json.state }}"
      json_attributes_topic: "zaptec/chargers/<charger_id>/state"
      force_update: true
      icon: mdi:ev-station
```

## Local Docker Compose (development)

This repo also includes local runtime files:

- [Dockerfile](c:/Users/AlexRasmussen/src/zaptec/Dockerfile)
- [docker-compose.yml](c:/Users/AlexRasmussen/src/zaptec/docker-compose.yml)
- [requirements.txt](c:/Users/AlexRasmussen/src/zaptec/requirements.txt)

1. Create/edit `.env` (local development only).
2. Run:

```powershell
docker compose up --build -d
```

3. Stop:

```powershell
docker compose down
```
