# Zaptec Service Bus Monitor

Version: `0.2.2`

## Dependency update (12 November 2026)

Both runtime requirements files pin the latest stable direct and transitive
Python dependencies verified from PyPI on this date, including
`azure-servicebus==7.15.0` and `paho-mqtt==2.2.0`. Both container images use
`python:3.15.2-slim`.

This project calls Zaptec's hosted cloud API directly; it does not depend on
a separately versioned Zaptec SDK. The current public OpenAPI specification
still identifies the API as `v1`: https://api.zaptec.com/swagger/v1/swagger.json.
Updating this project does not update charger firmware or the cloud service.

## Charging schedule observations

The charge status sensor's MQTT JSON attributes now preserve these current
Zaptec API observations by name:

| State ID | Attribute |
| --- | --- |
| 761 | `time_zone` |
| 762 | `time_schedule` |
| 763 | `next_schedule_event` |

These attributes appear after the corresponding Service Bus observation is
received. Empty values for 762/763 clear the previous cached schedule, including
the retained MQTT state. Older timestamped updates cannot restore a canceled
schedule. Raw observations remain available without discovery as usual.

For Monta-managed plans, enable the optional HTTP poller below. It adds three
date/time display sensors for calculated start, estimated completion, and latest
completion, plus connection-state and SoC sensors. Zaptec's raw schedule
observations remain available when sent by Service Bus.

The three Monta dates display in Copenhagen time as `dd/mm/yyyy hh.mm`
(24 hours), for example `13/11/2026 06.00`. Their original ISO timestamps
remain in the `estimated_start`, `estimated_complete`, and `latest_completion`
attributes for automation use. These display sensors have no timestamp device
class because Home Assistant requires ISO states for that class.

Live checks on 12 November 2026 authenticated successfully to Zaptec Service
Bus and Monta Public API. A continuous five-minute Service Bus receive session
delivered four voltage/operation-mode observations and zero observations for
762/763. During that check the user reported a plan visible in the NRGi phone
app with a 02:00â€“05:04 local charging window on 13 November.

Monta authentication granted the `all` scope. Both the charge-point list and
detail endpoints reported `busy-scheduled`, and the charge list and detail
endpoints reported the current session as `scheduled`. Those responses omitted
planned start/stop fields and returned `null` for `startedAt` and `stoppedAt`.
The Public API endpoints tested so far omit those future values. The
authenticated Monta Hub endpoint supplies the additional schedule data.
Monta Public API documentation is available at
https://docs.public-api.monta.com/reference/get-charge.

Local validation: `python -m unittest discover -s tests -v` and
`python -m pip check`. The Home Assistant app image was built and started on
HA01 on 12 November 2026; the standalone Compose deployment remains untested.

### Direct Monta Hub HTTP reader

`monta_charge_monitor.py` reads the latest charge through Monta Public API and
requests its extended schedule from the Hub endpoint
`https://hub.monta.app/api/gateway/api/v1/charges/<charge_id>`.
The live JSON response wraps the charge in `data`. It contains
`smart_charge.calculated_start_at` for the calculated start,
`smart_charge.stop_time` for the completion deadline, and
`smart_charge.max_kw` for the planner's charging-power value.
Public API bearer credentials received HTTP 401 from that Hub endpoint during
testing. A locally supplied authenticated Hub session is required. Direct HTTP
retrieval was verified on 12 November 2026, followed by MQTT delivery and state
readback of all five discovered sensors in HA01. This is an undocumented Hub
endpoint and may change independently of the Public API.

Set these values in the ignored `.env` file:

```dotenv
MONTA_CLIENT_ID=your-public-api-client-id
MONTA_CLIENT_SECRET=your-public-api-client-secret
MONTA_HUB_COOKIE="your-authenticated-Hub-request-Cookie-header-value"
MONTA_ENABLED=true
MONTA_CHARGE_POINT_ID=4199279
MONTA_OPERATOR_ID=1
MONTA_POLL_INTERVAL=30
MONTA_BATTERY_CAPACITY_KWH=61.0
MONTA_CHARGING_POWER_KW=10.4
```

The existing `MONTA_CLINT_ID` spelling is also accepted. Exporting the Hub
session initially uses the logged-in browser's Network request headers. The
reader then uses HTTP requests and requires no running browser. Refresh
`MONTA_HUB_COOKIE` when the session expires or is revoked.

Read once:

```powershell
.\.venv\Scripts\python monta_charge_monitor.py --charge-point-id 4199279
```

For repeated JSON output every 30 seconds, add `--watch`; press Ctrl+C to stop.
Output includes connection state, vehicle SoC, estimated start, calculated
completion, and latest completion. Defaults use the supplied 61.0 kWh usable
battery capacity and a 10.4 kW maximum vehicle charging power, with a 100% target
when the session has no explicit SoC limit. The calculation uses the lower of
the configured charging power and Monta's `max_kw` when available. In the
verified plan, Monta used 6.6 kW. From 67% SoC and a 01:59:49 start,
the calculated completion was 05:02:49 with a 06:00 deadline, all Copenhagen
time on 13 November. The estimate excludes losses, tapering, and pauses.
Capacity and vehicle power can be adjusted with `--capacity-kwh` and
`--power-kw`. Timestamps use Europe/Copenhagen by default.

### Home Assistant schedule sensors

The normal bridge entry point (`python zaptec_charge_monitor.py`) starts the
HTTP poller when `MONTA_ENABLED=true`. It shares the bridge's MQTT connection.
The HTTP poller continues to run during Service Bus reconnects. A bounded live
test verified repeated HTTP-to-MQTT updates. Deploy or start the bridge to keep
the sensors updated continuously.

The Docker image and Home Assistant app both include the poller. For Docker,
copy the Monta settings to the mounted `config/config.env`. In the Home
Assistant app, use the equivalent `monta_*` options in the Configuration tab.
Set `MQTT_DISCOVERY_ENABLED=true` for standalone deployments targeting Home
Assistant. The app enables discovery by default.

For charge point 4199279, the verified entity IDs are:

| Field | Entity ID |
| --- | --- |
| Car connection state | `sensor.monta_zap298581_schedule_car_connection_state` |
| SoC | `sensor.monta_zap298581_schedule_car_soc` |
| Estimated start | `sensor.monta_zap298581_schedule_estimated_charge_start` |
| Estimated completion | `sensor.monta_zap298581_schedule_estimated_charge_completion` |
| Latest completion | `sensor.monta_zap298581_schedule_latest_charge_completion` |

The state topic is `<MQTT_BASE_TOPIC>/monta/4199279/state`, and availability is
published on `<MQTT_BASE_TOPIC>/monta/4199279/availability`. State is not
retained. Sensors expire after at least 120 seconds without an update. Failed
HTTP reads mark the schedule sensors unavailable, and successful reads restore
them. Disconnecting the car clears the schedule timestamps. Expired Hub
sessions require a fresh Cookie value in the runtime configuration and a
bridge restart.

Version 0.2.2 is installed on HA01 as the local app
`local_zaptec_service_bus`, with automatic startup and watchdog enabled.
It polls Monta every 30 seconds without a browser. Local app updates require
copying the updated `zaptec_service_bus` directory into HA01's local apps
directory and refreshing the app store before updating or rebuilding.

This repository provides two ways to run the same Zaptec-to-MQTT bridge:

- a Home Assistant add-on with MQTT discovery enabled by default;
- a normal, Supervisor-independent Docker image with discovery disabled by default.

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
- Supports generic MQTT consumers without publishing Home Assistant discovery.

## Repository Layout

- [repository.yaml](c:/Users/AlexRasmussen/src/zaptec/repository.yaml): Home Assistant add-on repository metadata.
- [zaptec_service_bus/config.yaml](c:/Users/AlexRasmussen/src/zaptec/zaptec_service_bus/config.yaml): add-on manifest, options, schema, version.
- [zaptec_service_bus/Dockerfile](c:/Users/AlexRasmussen/src/zaptec/zaptec_service_bus/Dockerfile): app container build using the pinned Python image.
- [zaptec_service_bus/run.sh](c:/Users/AlexRasmussen/src/zaptec/zaptec_service_bus/run.sh): maps add-on options to env vars and starts monitor.
- [zaptec_service_bus/zaptec_charge_monitor.py](c:/Users/AlexRasmussen/src/zaptec/zaptec_service_bus/zaptec_charge_monitor.py): monitor runtime in container.

## Install In Home Assistant

1. In Home Assistant, go to `Settings -> Add-ons -> Add-on Store`.
2. Click menu (`â‹®`) -> `Repositories`.
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
- `mqtt_discovery_enabled` (default `true`)
- `mqtt_retain` (default `true`)
- `log_level` (`ERROR`, `INFO`, `DEBUG`, default `INFO`)

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
mqtt_discovery_enabled: true
mqtt_retain: true
log_level: "INFO"
```

Message payload logging is only emitted when `log_level` is set to `DEBUG`.

## Refresh Zaptec Messaging Credentials

`get_zaptec_messaging_credentials.py` requests a short-lived Zaptec bearer token
and then retrieves fresh AMQP/Service Bus connection details for a user group.
The username can be supplied by environment variable, while the password is
prompted without echoing it:

```powershell
$env:ZAPTEC_USERNAME = "service-account@example.com"
python .\get_zaptec_messaging_credentials.py <user-group-uuid>
```

For automation, set `ZAPTEC_USER_GROUP_ID` and `ZAPTEC_PASSWORD` as secrets. An
existing token can instead be supplied through `ZAPTEC_ACCESS_TOKEN` or
`--access-token`. The script writes the API's JSON response to standard output,
so treat its output as secret material and do not commit it.

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

## Standalone Docker

The root image is a normal Linux container and does not use the Home Assistant
Supervisor or add-on base images. It publishes JSON to
`<MQTT_BASE_TOPIC>/chargers/<charger_id>/state`, so it works with any MQTT
consumer. Home Assistant discovery is disabled in the supplied Compose file.

1. Create the host configuration directory and copy the template:

```powershell
New-Item -ItemType Directory -Force config
Copy-Item config/config.env.example config/config.env
```

2. Fill in the Azure Service Bus and MQTT values in `config/config.env`.
3. Build and run:

```powershell
docker compose up --build -d
```

4. Inspect status and logs:

```powershell
docker compose ps
docker compose logs -f zaptec-service-bus
```

5. Stop:

```powershell
docker compose down
```

The Compose service maps `./config` on the host to the container's `/config`
directory as read-only. The application reads `/config/config.env`. Environment
variables supplied directly to the container take precedence over the file.

To publish Home Assistant discovery from the standalone container, set
`MQTT_DISCOVERY_ENABLED=true` in `config/config.env`.

The container runs as an unprivileged user and includes a health check. Its
build context excludes the live configuration file, so credentials are not sent
to the Docker daemon.
