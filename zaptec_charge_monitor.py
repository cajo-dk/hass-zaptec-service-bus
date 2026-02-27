import json
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
from azure.servicebus import ServiceBusClient, ServiceBusReceiveMode, TransportType

STATE_710_MAP = {
    1: "disconnected",
    2: "connected_requesting_charge",
    3: "charging",
    5: "connected_finished_idle",
}

STATE_ID_NAMES = {
    100: "device_info",
    150: "active_network",
    151: "online",
    157: "iot_hub",
    158: "iot_device_id",
    160: "profile",
    201: "internal_temp",
    202: "external_temp",
    204: "power_board_temp",
    206: "mcu_temp",
    207: "ambient_temp",
    220: "connector_temp",
    270: "total_energy",
    501: "voltage_phase_1",
    502: "voltage_phase_2",
    503: "voltage_phase_3",
    507: "current_phase_1",
    508: "current_phase_2",
    509: "current_phase_3",
    510: "max_current",
    511: "min_current",
    513: "total_charge_power",
    519: "phases",
    520: "phase_mode",
    522: "fuse_size",
    523: "cable_current_limit",
    553: "session_energy",
    554: "meter_reading",
    702: "charging_current",
    708: "available_current",
    710: "charger_operation_mode",
    711: "authentication_enabled",
    712: "lock_status",
    718: "rcd_trip_status",
    723: "last_session",
    751: "uptime_seconds",
    800: "installation_id",
    801: "charger_group",
    802: "serial_number",
    808: "debug_status",
    809: "signal_strength",
    908: "firmware_version",
    911: "charger_fw",
    916: "platform_version",
}

NUMERIC_STATE_IDS = {
    151,
    201,
    202,
    204,
    206,
    207,
    220,
    270,
    501,
    502,
    503,
    507,
    508,
    509,
    510,
    511,
    513,
    519,
    520,
    522,
    523,
    553,
    702,
    708,
    711,
    712,
    718,
    751,
    808,
    809,
}

NUMERIC_ATTRIBUTE_DEFAULTS = {STATE_ID_NAMES[state_id]: 0 for state_id in NUMERIC_STATE_IDS}
FORCE_ZERO_WHEN_NOT_CHARGING_STATE_IDS = {513, 501, 502, 503, 507, 508, 509}
FORCE_ZERO_WHEN_NOT_CHARGING_ATTRS = {
    STATE_ID_NAMES[state_id] for state_id in FORCE_ZERO_WHEN_NOT_CHARGING_STATE_IDS
}


def load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer.") from exc


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


LOG_LEVEL_ORDER = {"DEBUG": 10, "INFO": 20, "ERROR": 40}


def parse_log_level(raw: str | None) -> str:
    value = (raw or "INFO").strip().upper()
    if value not in LOG_LEVEL_ORDER:
        raise ValueError("LOG_LEVEL must be one of: ERROR, INFO, DEBUG")
    return value


def should_log(current_level: str, event_level: str) -> bool:
    return LOG_LEVEL_ORDER[event_level] >= LOG_LEVEL_ORDER[current_level]


def log_line(current_level: str, event_level: str, message: str) -> None:
    if should_log(current_level, event_level):
        print(f"[{event_level}] {message}")


def parse_receive_mode(raw: str) -> ServiceBusReceiveMode:
    normalized = raw.strip().lower()
    if normalized in ("peek_lock", "peeklock"):
        return ServiceBusReceiveMode.PEEK_LOCK
    if normalized in ("receive_and_delete", "receiveanddelete"):
        return ServiceBusReceiveMode.RECEIVE_AND_DELETE
    raise ValueError("AZURE_SERVICE_BUS_RECEIVE_MODE must be peek_lock or receive_and_delete")


def parse_transport_type(raw: str) -> TransportType:
    normalized = raw.strip().lower().replace("-", "_")
    if normalized in ("amqp", "aqmp"):
        return TransportType.Amqp
    if normalized in ("amqp_over_websocket", "amqp_websocket", "websocket", "websockets"):
        return TransportType.AmqpOverWebsocket
    raise ValueError("AZURE_SERVICE_BUS_TRANSPORT must be amqp or amqp_over_websocket")


def parse_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool, dict, list)):
        return value
    text = str(value).strip()
    if text == "":
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def sanitize_id(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def build_initial_attributes(device_id: str, charger_id: str) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "device_id": device_id,
        "charger_id": charger_id,
        "state_710_raw": 0,
    }
    attrs.update(NUMERIC_ATTRIBUTE_DEFAULTS)
    return attrs


def build_initial_state_attributes() -> dict[str, Any]:
    return dict(NUMERIC_ATTRIBUTE_DEFAULTS)


def try_coerce_numeric(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    return None


def parse_message_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        numeric = float(value)
        # Treat large values as milliseconds since epoch.
        if numeric > 1e12:
            numeric /= 1000.0
        try:
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def should_apply_update(
    field_timestamps: dict[str, datetime],
    field_name: str,
    message_timestamp: datetime | None,
) -> bool:
    if message_timestamp is None:
        return True
    previous_timestamp = field_timestamps.get(field_name)
    return previous_timestamp is None or message_timestamp >= previous_timestamp


def apply_cached_update(
    state_attrs: dict[str, Any],
    field_timestamps: dict[str, datetime],
    field_name: str,
    value: Any,
    message_timestamp: datetime | None,
    log_level: str,
) -> bool:
    if not should_apply_update(field_timestamps, field_name, message_timestamp):
        previous_timestamp = field_timestamps.get(field_name)
        log_line(
            log_level,
            "DEBUG",
            (
                f"Dropped stale update for {field_name}: "
                f"incoming_ts={message_timestamp.isoformat() if message_timestamp else 'none'} "
                f"< cached_ts={previous_timestamp.isoformat() if previous_timestamp else 'none'}"
            ),
        )
        return False
    state_attrs[field_name] = value
    if message_timestamp is not None:
        field_timestamps[field_name] = message_timestamp
    return True


def try_extract_json_from_bytes(raw: bytes) -> Any | None:
    start = raw.find(b"{")
    end = raw.rfind(b"}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = raw[start : end + 1]
    try:
        return json.loads(candidate.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def decode_message_body(message: Any) -> Any:
    try:
        raw = b"".join(
            part if isinstance(part, (bytes, bytearray)) else str(part).encode("utf-8")
            for part in message.body
        )
    except TypeError:
        raw = str(message.body).encode("utf-8")

    extracted = try_extract_json_from_bytes(raw)
    if extracted is not None:
        return extracted
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"_binary_hex": raw.hex()}


def create_mqtt_client() -> mqtt.Client:
    client_id = os.getenv("MQTT_CLIENT_ID", "zaptec-charge-monitor")
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)

    username = os.getenv("MQTT_USERNAME")
    password = os.getenv("MQTT_PASSWORD")
    if username:
        mqtt_client.username_pw_set(username, password=password)

    mqtt_client.connect(require_env("MQTT_HOST"), env_int("MQTT_PORT", 1883), env_int("MQTT_KEEPALIVE", 60))
    mqtt_client.loop_start()
    return mqtt_client


def publish_discovery(
    mqtt_client: mqtt.Client,
    discovery_prefix: str,
    base_topic: str,
    charger_key: str,
    device_name: str,
    device_id: str,
) -> str:
    safe_key = sanitize_id(charger_key)
    state_topic = f"{base_topic}/chargers/{safe_key}/state"
    discovery_topic = f"{discovery_prefix}/sensor/zaptec_{safe_key}/config"
    payload = {
        "name": f"{device_name} Charge Status",
        "unique_id": f"zaptec_{safe_key}_charge_status",
        "state_topic": state_topic,
        "value_template": "{{ value_json.state }}",
        "json_attributes_topic": state_topic,
        "force_update": True,
        "icon": "mdi:ev-station",
        "device": {
            "identifiers": [f"zaptec_{safe_key}"],
            "manufacturer": "Zaptec",
            "name": device_name,
            "model": "Zaptec Charger",
            "serial_number": device_id,
        },
    }
    mqtt_client.publish(discovery_topic, json.dumps(payload), qos=1, retain=True)
    return state_topic


def main() -> int:
    load_dotenv(".env")

    connection_string = require_env("AZURE_SERVICE_BUS_CONNECTION_STRING")
    topic_name = require_env("AZURE_SERVICE_BUS_TOPIC_NAME")
    subscription_name = require_env("AZURE_SERVICE_BUS_SUBSCRIPTION_NAME")
    max_wait_time = env_int("AZURE_SERVICE_BUS_MAX_WAIT_TIME", 5)
    receive_mode = parse_receive_mode(os.getenv("AZURE_SERVICE_BUS_RECEIVE_MODE", "peek_lock"))
    transport_type = parse_transport_type(os.getenv("AZURE_SERVICE_BUS_TRANSPORT", "amqp"))

    discovery_prefix = os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant").strip("/")
    base_topic = os.getenv("MQTT_BASE_TOPIC", "zaptec").strip("/")
    retain = env_bool("MQTT_RETAIN", True)
    log_level = parse_log_level(os.getenv("LOG_LEVEL", "INFO"))

    mqtt_client = create_mqtt_client()

    stop_requested = False
    published_discovery: set[str] = set()
    charger_state_cache: dict[str, dict[str, Any]] = {}

    def handle_signal(sig: int, _frame: Any) -> None:
        nonlocal stop_requested
        if not stop_requested:
            log_line(log_level, "INFO", f"Received signal {sig}; shutting down...")
        stop_requested = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    with ServiceBusClient.from_connection_string(connection_string, transport_type=transport_type) as sb_client:
        with sb_client.get_subscription_receiver(
            topic_name=topic_name,
            subscription_name=subscription_name,
            receive_mode=receive_mode,
        ) as receiver:
            log_line(log_level, "INFO", "Listening for messages. Press Ctrl-C to stop.")
            while not stop_requested:
                messages = receiver.receive_messages(max_message_count=10, max_wait_time=max_wait_time)
                if not messages:
                    continue

                for message in messages:
                    body = decode_message_body(message)
                    if not isinstance(body, dict):
                        log_line(log_level, "DEBUG", json.dumps({"ignored_body": body}, default=str))
                        if receive_mode == ServiceBusReceiveMode.PEEK_LOCK:
                            receiver.complete_message(message)
                        continue

                    state_id = parse_value(body.get("StateId"))
                    charger_id = str(body.get("ChargerId") or body.get("DeviceId") or "unknown")
                    device_id = str(body.get("DeviceId") or charger_id)
                    device_name = f"Zaptec {device_id}"
                    timestamp = body.get("Timestamp")

                    cache = charger_state_cache.setdefault(
                        charger_id,
                        {
                            "state": "unknown",
                            "attributes": build_initial_attributes(device_id, charger_id),
                            "state_attributes": build_initial_state_attributes(),
                            "field_timestamps": {},
                            "state_timestamp": None,
                        },
                    )
                    attrs = cache["attributes"]
                    state_attrs = cache["state_attributes"]
                    field_timestamps = cache["field_timestamps"]
                    state_timestamp = cache["state_timestamp"]
                    attrs["device_id"] = device_id
                    attrs["charger_id"] = charger_id

                    value_parsed = parse_value(body.get("Value"))
                    if value_parsed is None:
                        value_parsed = parse_value(body.get("ValueAsString"))
                    message_timestamp = parse_message_timestamp(timestamp)

                    if state_id == 710:
                        operation_mode_value = parse_value(body.get("ValueAsString"))
                        if operation_mode_value is None:
                            operation_mode_value = parse_value(body.get("Value"))
                        if isinstance(operation_mode_value, str) and operation_mode_value.isdigit():
                            operation_mode_value = int(operation_mode_value)
                        if state_timestamp is None or message_timestamp is None or message_timestamp >= state_timestamp:
                            cache["state"] = STATE_710_MAP.get(
                                operation_mode_value,
                                f"unknown_{operation_mode_value}",
                            )
                            cache["state_timestamp"] = message_timestamp
                        else:
                            log_line(
                                log_level,
                                "DEBUG",
                                (
                                    "Dropped stale state update for state_710: "
                                    f"incoming_ts={message_timestamp.isoformat() if message_timestamp else 'none'} "
                                    f"< cached_ts={state_timestamp.isoformat() if state_timestamp else 'none'}"
                                ),
                            )
                        operation_mode_numeric = try_coerce_numeric(operation_mode_value)
                        if operation_mode_numeric is not None:
                            operation_mode_updated = apply_cached_update(
                                state_attrs,
                                field_timestamps,
                                "state_710_raw",
                                operation_mode_numeric,
                                message_timestamp,
                                log_level,
                            )
                            if operation_mode_numeric != 3 and operation_mode_updated:
                                for attribute_name in FORCE_ZERO_WHEN_NOT_CHARGING_ATTRS:
                                    apply_cached_update(
                                        state_attrs,
                                        field_timestamps,
                                        attribute_name,
                                        0,
                                        message_timestamp,
                                        log_level,
                                    )
                    elif isinstance(state_id, int):
                        name = STATE_ID_NAMES.get(state_id, f"stateid_{state_id}")
                        if state_id in NUMERIC_STATE_IDS:
                            numeric_value = try_coerce_numeric(value_parsed)
                            if numeric_value is not None:
                                operation_mode = state_attrs.get("state_710_raw", 0)
                                if (
                                    name in FORCE_ZERO_WHEN_NOT_CHARGING_ATTRS
                                    and operation_mode != 3
                                ):
                                    numeric_value = 0
                                apply_cached_update(
                                    state_attrs,
                                    field_timestamps,
                                    name,
                                    numeric_value,
                                    message_timestamp,
                                    log_level,
                                )
                        elif value_parsed is not None:
                            apply_cached_update(
                                state_attrs,
                                field_timestamps,
                                name,
                                value_parsed,
                                message_timestamp,
                                log_level,
                            )

                    # Rebuild outgoing attributes from independently cached state attributes.
                    attrs.update(state_attrs)

                    attrs["last_state_id"] = state_id
                    attrs["last_message_timestamp"] = timestamp
                    attrs["last_updated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

                    if charger_id not in published_discovery:
                        publish_discovery(mqtt_client, discovery_prefix, base_topic, charger_id, device_name, device_id)
                        published_discovery.add(charger_id)

                    state_topic = f"{base_topic}/chargers/{sanitize_id(charger_id)}/state"
                    outgoing = {"state": cache["state"], **attrs}
                    mqtt_client.publish(state_topic, json.dumps(outgoing, default=str), qos=1, retain=retain)
                    log_line(log_level, "DEBUG", json.dumps(outgoing, indent=2, default=str))

                    if receive_mode == ServiceBusReceiveMode.PEEK_LOCK:
                        receiver.complete_message(message)

    mqtt_client.loop_stop()
    mqtt_client.disconnect()
    log_line(log_level, "INFO", "Monitor stopped.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as err:
        print(f"Configuration error: {err}", file=sys.stderr)
        raise SystemExit(2)
