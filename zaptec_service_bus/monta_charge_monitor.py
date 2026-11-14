"""Read Monta charging plans over HTTP using a locally supplied Hub session."""

import argparse
import json
import math
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests

from zaptec_charge_monitor import (
    env_bool, env_int, load_dotenv, log_line, parse_message_timestamp, require_env,
)


PUBLIC_API = "https://public-api.monta.com/api/v1"
HUB_API = "https://hub.monta.app/api/gateway/api/v1"
ACTIVE_STATES = {"starting", "scheduled", "charging", "paused", "stopping"}


class MontaReadError(RuntimeError):
    """A read or authentication request failed without exposing credentials."""


class MontaClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.access_token = ""
        self.token_expires_at = 0.0

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        try:
            response = self.session.request(
                method, url, timeout=10, allow_redirects=False, **kwargs
            )
        except requests.RequestException as error:
            raise MontaReadError("Monta HTTP connection failed") from error
        if response.status_code in (301, 302, 303, 307, 308, 401, 403):
            source = "Hub session" if url.startswith(HUB_API) else "Public API credentials"
            raise MontaReadError(
                f"{source} rejected (HTTP {response.status_code}). "
                "Refresh the corresponding credentials in .env."
            )
        if not response.ok:
            raise MontaReadError(f"Monta request failed (HTTP {response.status_code})")
        try:
            return response.json()
        except ValueError as error:
            raise MontaReadError("Monta returned an unexpected non-JSON response") from error

    def authenticate(self) -> None:
        client_id = os.getenv("MONTA_CLIENT_ID") or os.getenv("MONTA_CLINT_ID")
        if not client_id:
            raise ValueError("Set MONTA_CLIENT_ID in .env")
        auth = self.request(
            "POST",
            f"{PUBLIC_API}/auth/token",
            json={"clientId": client_id, "clientSecret": require_env("MONTA_CLIENT_SECRET")},
        )
        if not isinstance(auth, dict) or not auth.get("accessToken"):
            raise MontaReadError("Monta authentication response omitted the access token")
        self.access_token = auth["accessToken"]
        expiration = parse_message_timestamp(auth.get("accessTokenExpirationDate"))
        self.token_expires_at = expiration.timestamp() - 60 if expiration else time.time() + 3000

    def public_get(self, path: str) -> Any:
        if time.time() >= self.token_expires_at:
            self.authenticate()
        return self.request(
            "GET", f"{PUBLIC_API}{path}",
            headers={"Authorization": f"Bearer {self.access_token}", "Accept": "application/json"},
        )

    def read(self, charge_point_id: int) -> tuple[dict, dict, dict]:
        point = self.public_get(f"/charge-points/{charge_point_id}")
        response = self.public_get(f"/charges?chargePointId={charge_point_id}&perPage=1")
        charges = response.get("data") if isinstance(response, dict) else None
        if not isinstance(point, dict) or not isinstance(charges, list):
            raise MontaReadError("Unexpected Monta charge-point or charge-list response")
        if not charges:
            return point, {}, {}
        charge = charges[0]
        if not isinstance(charge, dict) or "id" not in charge:
            raise MontaReadError("Unexpected Monta charge response")
        if charge.get("state") not in ACTIVE_STATES:
            return point, charge, {}
        cookie = require_env("MONTA_HUB_COOKIE")
        if "\n" in cookie or "\r" in cookie:
            raise ValueError("MONTA_HUB_COOKIE must be a single-line Cookie header value")
        detail = self.request(
            "GET", f"{HUB_API}/charges/{charge['id']}",
            headers={
                "Accept": "application/json",
                "Cookie": cookie,
                "x-hub-operator-override": os.getenv("MONTA_OPERATOR_ID", "1"),
            },
        )
        if isinstance(detail, dict) and "data" in detail:
            detail = detail["data"]
        if not isinstance(detail, dict) or str(detail.get("id")) != str(charge["id"]):
            raise MontaReadError("Unexpected Monta Hub charge-detail response")
        return point, charge, detail


def build_snapshot(
    point: dict, charge: dict, detail: dict, *,
    capacity_kwh: float, power_kw: float, now: datetime,
) -> dict[str, Any]:
    """Estimate battery completion at constant power, with no loss/taper allowance."""
    if not all(math.isfinite(value) and value > 0 for value in (capacity_kwh, power_kw)):
        raise ValueError("Battery capacity and charging power must be positive finite numbers")
    soc = (charge.get("soc") or {}).get("percentage")
    target = charge.get("socLimit")
    if target is None:
        target = 100.0
    valid_soc = (
        isinstance(soc, (int, float)) and not isinstance(soc, bool)
        and math.isfinite(soc) and 0 <= soc <= 100
    )
    valid_target = (
        isinstance(target, (int, float)) and not isinstance(target, bool)
        and math.isfinite(target) and 0 <= target <= 100
    )
    smart = detail.get("smart_charge") or detail.get("smartCharge") or {}
    active = charge.get("state") in ACTIVE_STATES and point.get("cablePluggedIn") is True
    start = parse_message_timestamp(
        smart.get("calculated_start_at") or smart.get("calculatedStartAt")
        or detail.get("scheduled_start_at") or detail.get("scheduledStartAt")
    )
    deadline = parse_message_timestamp(
        smart.get("stop_time") or smart.get("stopTime")
        or detail.get("scheduled_stop_at") or detail.get("scheduledStopAt")
    )
    planner_power = smart.get("max_kw")
    if not (
        isinstance(planner_power, (int, float)) and not isinstance(planner_power, bool)
        and math.isfinite(planner_power) and planner_power >= 0
    ):
        planner_power = None
    effective_power = min(power_kw, planner_power) if planner_power is not None else power_kw
    complete = None
    if active and valid_soc and valid_target and effective_power > 0:
        anchor = now if charge.get("state") == "charging" else start
        if anchor is not None and anchor >= now:
            energy_kwh = capacity_kwh * max(target - soc, 0) / 100
            complete = anchor + timedelta(hours=energy_kwh / effective_power)
    return {
        "checked_at": now.isoformat(),
        "charge_point_id": str(point.get("id", "")),
        "charge_id": str(charge.get("id", "")),
        "serial_number": point.get("serialNumber"),
        "connection_state": "disconnected" if point.get("cablePluggedIn") is False else point.get("state", "unknown"),
        "soc": soc if valid_soc else None,
        "target_soc": target if valid_target else None,
        "estimated_start": start.isoformat() if active and start else None,
        "estimated_complete": complete.isoformat() if complete else None,
        "latest_completion": deadline.isoformat() if active and deadline else None,
        "battery_capacity_kwh": capacity_kwh,
        "configured_power_kw": power_kw,
        "planner_power_kw": planner_power,
        "effective_power_kw": effective_power,
        "estimate_assumption": f"{capacity_kwh:g} kWh usable battery, constant {effective_power:g} kW into battery",
    }


SCHEDULE_SENSORS = {
    "connection_state": ("Car Connection State", None, None),
    "soc": ("Car SoC", "battery", "%"),
    "estimated_start": ("Estimated Charge Start", None, None),
    "estimated_complete": ("Estimated Charge Completion", None, None),
    "latest_completion": ("Latest Charge Completion", None, None),
}

SCHEDULE_DATE_FIELDS = ("estimated_start", "estimated_complete", "latest_completion")


def schedule_display_values(snapshot: dict, zone: str = "Europe/Copenhagen") -> dict:
    """Keep ISO timestamps for consumers and add explicit local display strings."""
    local_zone = ZoneInfo(zone)
    return {
        f"{field}_display": (
            datetime.fromisoformat(snapshot[field]).astimezone(local_zone).strftime("%d/%m/%Y %H.%M")
            if snapshot[field] else None
        )
        for field in SCHEDULE_DATE_FIELDS
    }


def publish_monta_snapshot(
    mqtt_client: Any, snapshot: dict, *, base_topic: str, discovery_prefix: str,
    discovery_enabled: bool, publish_config: bool, interval: int,
) -> None:
    point_id = snapshot["charge_point_id"]
    topic = f"{base_topic}/monta/{point_id}"
    if discovery_enabled and publish_config:
        device = {
            "identifiers": [f"monta_schedule_{point_id}"],
            "manufacturer": "Monta",
            "name": f"Monta {snapshot.get('serial_number') or point_id} Schedule",
            "model": "Charging plan",
        }
        for field, (name, device_class, unit) in SCHEDULE_SENSORS.items():
            state_field = f"{field}_display" if field in SCHEDULE_DATE_FIELDS else field
            payload = {
                "name": name,
                "unique_id": f"monta_{point_id}_{field}",
                "state_topic": f"{topic}/state",
                "value_template": "{{ value_json." + state_field + " if value_json." + state_field + " is not none else 'None' }}",
                "json_attributes_topic": f"{topic}/state",
                "availability_topic": f"{topic}/availability",
                "expire_after": max(120, interval * 3),
                "device": device,
            }
            if device_class:
                payload["device_class"] = device_class
            elif field in SCHEDULE_DATE_FIELDS:
                payload["icon"] = "mdi:calendar-clock"
            if unit:
                payload["unit_of_measurement"] = unit
            mqtt_client.publish(
                f"{discovery_prefix}/sensor/monta_{point_id}_{field}/config",
                json.dumps(payload), qos=1, retain=True,
            )
    # Let HA restore its expiry timer instead of replaying stale retained state.
    mqtt_client.publish(f"{topic}/state", json.dumps({**snapshot, **schedule_display_values(snapshot)}), qos=1, retain=False)
    mqtt_client.publish(f"{topic}/availability", "online", qos=1, retain=True)


def run_monta_poller(mqtt_client: Any, stop: threading.Event, log_level: str) -> None:
    """Publish optional Monta schedule sensors alongside Service Bus telemetry."""
    point_id = env_int("MONTA_CHARGE_POINT_ID", 0)
    interval = env_int("MONTA_POLL_INTERVAL", 30)
    base_topic = os.getenv("MQTT_BASE_TOPIC", "zaptec").strip("/")
    discovery_prefix = os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant").strip("/")
    client = MontaClient()
    published_config = False
    try:
        while not stop.is_set():
            try:
                point, charge, detail = client.read(point_id)
                snapshot = build_snapshot(
                    point, charge, detail,
                    capacity_kwh=float(os.getenv("MONTA_BATTERY_CAPACITY_KWH", "61")),
                    power_kw=float(os.getenv("MONTA_CHARGING_POWER_KW", "10.4")),
                    now=datetime.now(timezone.utc),
                )
                publish_monta_snapshot(
                    mqtt_client, snapshot, base_topic=base_topic,
                    discovery_prefix=discovery_prefix,
                    discovery_enabled=env_bool("MQTT_DISCOVERY_ENABLED", True),
                    publish_config=not published_config, interval=interval,
                )
                published_config = True
            except (MontaReadError, ValueError) as error:
                mqtt_client.publish(f"{base_topic}/monta/{point_id}/availability", "offline", qos=1, retain=True)
                log_line(log_level, "ERROR", f"Monta schedule read failed: {error}")
            if stop.wait(interval):
                break
    finally:
        mqtt_client.publish(f"{base_topic}/monta/{point_id}/availability", "offline", qos=1, retain=True)
        client.session.close()


def main() -> int:
    load_dotenv(os.getenv("CONFIG_FILE", ".env"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--charge-point-id", type=int, default=os.getenv("MONTA_CHARGE_POINT_ID"))
    parser.add_argument("--watch", action="store_true", help="Repeat until interrupted")
    parser.add_argument("--interval", type=float, default=30)
    parser.add_argument("--capacity-kwh", type=float, default=61.0)
    parser.add_argument("--power-kw", type=float, default=10.4)
    parser.add_argument("--timezone", default="Europe/Copenhagen")
    args = parser.parse_args()
    if not args.charge_point_id or args.charge_point_id <= 0:
        parser.error("Provide --charge-point-id or MONTA_CHARGE_POINT_ID")
    if not math.isfinite(args.interval) or args.interval < 30:
        parser.error("--interval must be at least 30 seconds")
    local_zone = ZoneInfo(args.timezone)
    client = MontaClient()
    try:
        while True:
            point, charge, detail = client.read(args.charge_point_id)
            snapshot = build_snapshot(
                point, charge, detail, capacity_kwh=args.capacity_kwh,
                power_kw=args.power_kw, now=datetime.now(timezone.utc),
            )
            display = schedule_display_values(snapshot, args.timezone)
            for key in SCHEDULE_DATE_FIELDS:
                snapshot[key] = display[f"{key}_display"]
            for key in ("checked_at",):
                if snapshot[key]:
                    snapshot[key] = datetime.fromisoformat(snapshot[key]).astimezone(local_zone).isoformat()
            print(json.dumps(snapshot), flush=True)
            if not args.watch:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    finally:
        client.session.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, MontaReadError) as error:
        log_line("ERROR", "ERROR", f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
