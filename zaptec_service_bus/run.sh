#!/usr/bin/with-contenv bashio

set -euo pipefail

export AZURE_SERVICE_BUS_CONNECTION_STRING="$(bashio::config 'azure_service_bus_connection_string')"
export AZURE_SERVICE_BUS_TOPIC_NAME="$(bashio::config 'azure_service_bus_topic_name')"
export AZURE_SERVICE_BUS_SUBSCRIPTION_NAME="$(bashio::config 'azure_service_bus_subscription_name')"
export AZURE_SERVICE_BUS_MAX_WAIT_TIME="$(bashio::config 'azure_service_bus_max_wait_time')"
export AZURE_SERVICE_BUS_RECEIVE_MODE="$(bashio::config 'azure_service_bus_receive_mode')"
export AZURE_SERVICE_BUS_TRANSPORT="$(bashio::config 'azure_service_bus_transport')"

export MQTT_HOST="$(bashio::config 'mqtt_host')"
export MQTT_PORT="$(bashio::config 'mqtt_port')"
export MQTT_USERNAME="$(bashio::config 'mqtt_username')"
export MQTT_PASSWORD="$(bashio::config 'mqtt_password')"
export MQTT_KEEPALIVE="$(bashio::config 'mqtt_keepalive')"
export MQTT_CLIENT_ID="$(bashio::config 'mqtt_client_id')"
export MQTT_BASE_TOPIC="$(bashio::config 'mqtt_base_topic')"
export MQTT_DISCOVERY_PREFIX="$(bashio::config 'mqtt_discovery_prefix')"
export MQTT_RETAIN="$(bashio::config 'mqtt_retain')"

exec python3 /app/zaptec_charge_monitor.py
