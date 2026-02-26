#!/bin/sh
set -eu

OPTIONS_FILE="/data/options.json"

read_option() {
  python3 - "$1" "$OPTIONS_FILE" <<'PY'
import json
import sys

key = sys.argv[1]
path = sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
value = data.get(key, "")
if isinstance(value, bool):
    print("true" if value else "false")
elif value is None:
    print("")
else:
    print(value)
PY
}

export AZURE_SERVICE_BUS_CONNECTION_STRING="$(read_option azure_service_bus_connection_string)"
export AZURE_SERVICE_BUS_TOPIC_NAME="$(read_option azure_service_bus_topic_name)"
export AZURE_SERVICE_BUS_SUBSCRIPTION_NAME="$(read_option azure_service_bus_subscription_name)"
export AZURE_SERVICE_BUS_MAX_WAIT_TIME="$(read_option azure_service_bus_max_wait_time)"
export AZURE_SERVICE_BUS_RECEIVE_MODE="$(read_option azure_service_bus_receive_mode)"
export AZURE_SERVICE_BUS_TRANSPORT="$(read_option azure_service_bus_transport)"

export MQTT_HOST="$(read_option mqtt_host)"
export MQTT_PORT="$(read_option mqtt_port)"
export MQTT_USERNAME="$(read_option mqtt_username)"
export MQTT_PASSWORD="$(read_option mqtt_password)"
export MQTT_KEEPALIVE="$(read_option mqtt_keepalive)"
export MQTT_CLIENT_ID="$(read_option mqtt_client_id)"
export MQTT_BASE_TOPIC="$(read_option mqtt_base_topic)"
export MQTT_DISCOVERY_PREFIX="$(read_option mqtt_discovery_prefix)"
export MQTT_RETAIN="$(read_option mqtt_retain)"
export LOG_LEVEL="$(read_option log_level)"

exec python3 /app/zaptec_charge_monitor.py
