from datetime import datetime, timezone
import unittest
from unittest.mock import Mock, patch
import json

import requests

from monta_charge_monitor import MontaClient, MontaReadError, build_snapshot, publish_monta_snapshot, schedule_display_values


class MontaScheduleTests(unittest.TestCase):
    def setUp(self):
        self.point = {"id": 1, "state": "busy-scheduled", "cablePluggedIn": True}
        self.charge = {
            "id": 900000000000000001, "state": "scheduled",
            "soc": {"percentage": 67}, "socLimit": 100,
        }
        self.detail = {"smartCharge": {
            "calculatedStartAt": "2026-11-13T00:59:00Z",
            "stopTime": "2026-11-13T05:00:00Z",
        }}
        self.now = datetime(2026, 11, 12, 20, tzinfo=timezone.utc)

    def snapshot(self, now=None):
        return build_snapshot(
            self.point, self.charge, self.detail, capacity_kwh=61,
            power_kw=10.4, now=now or self.now,
        )

    def test_user_example_and_deadline_have_separate_meanings(self):
        snapshot = self.snapshot()
        complete = datetime.fromisoformat(snapshot["estimated_complete"])
        self.assertEqual(complete.hour, 2)
        self.assertEqual(complete.minute, 55)
        self.assertEqual(snapshot["latest_completion"], "2026-11-13T05:00:00+00:00")
        self.assertEqual(snapshot["charge_id"], "900000000000000001")

    def test_disconnection_clears_all_schedule_outputs(self):
        self.point["cablePluggedIn"] = False
        snapshot = self.snapshot()
        self.assertEqual(snapshot["connection_state"], "disconnected")
        for field in ("estimated_start", "estimated_complete", "latest_completion"):
            self.assertIsNone(snapshot[field])

    def test_missing_soc_does_not_become_zero(self):
        self.charge["soc"] = None
        snapshot = self.snapshot()
        self.assertIsNone(snapshot["soc"])
        self.assertIsNone(snapshot["estimated_complete"])
        self.assertIsNotNone(snapshot["estimated_start"])

    def test_live_snake_case_plan_respects_its_lower_power_limit(self):
        self.detail = {"smart_charge": {
            "calculated_start_at": "2026-11-13T00:59:49Z",
            "stop_time": "2026-11-13T05:00:00Z",
            "max_kw": 6.6,
        }}
        snapshot = self.snapshot()
        self.assertEqual(snapshot["estimated_complete"], "2026-11-13T04:02:49+00:00")
        self.assertEqual(snapshot["effective_power_kw"], 6.6)
        self.assertEqual(snapshot["configured_power_kw"], 10.4)

    def test_zero_plan_power_leaves_completion_unknown(self):
        self.detail = {"smart_charge": {"calculated_start_at": "2026-11-13T00:59:49Z", "max_kw": 0}}
        self.assertIsNone(self.snapshot()["estimated_complete"])

    def test_hub_data_envelope_is_unwrapped_and_session_id_checked(self):
        client = MontaClient()
        client.public_get = Mock(side_effect=[self.point, {"data": [self.charge]}])
        client.request = Mock(return_value={"data": {"id": self.charge["id"], **self.detail}})
        with patch.dict("os.environ", {"MONTA_HUB_COOKIE": "session=test"}):
            _, _, detail = client.read(1)
        self.assertEqual(detail["id"], self.charge["id"])
        self.assertNotIn("data", detail)
        client.public_get.reset_mock(side_effect=True)
        client.public_get.side_effect = [self.point, {"data": [self.charge]}]
        client.request.return_value = {"data": {"id": 2}}
        with patch.dict("os.environ", {"MONTA_HUB_COOKIE": "session=test"}):
            with self.assertRaises(MontaReadError):
                client.read(1)

    def test_discovery_exposes_five_sensors_and_expires_stale_data(self):
        mqtt = Mock()
        publish_monta_snapshot(
            mqtt, self.snapshot(), base_topic="zaptec", discovery_prefix="homeassistant",
            discovery_enabled=True, publish_config=True, interval=30,
        )
        configs = [json.loads(call.args[1]) for call in mqtt.publish.call_args_list
                   if call.args[0].endswith("/config")]
        self.assertEqual(len(configs), 5)
        self.assertEqual(sum(config.get("device_class") == "timestamp" for config in configs), 0)
        self.assertEqual(sum("_display" in config["value_template"] for config in configs), 3)
        self.assertTrue(all(config["expire_after"] == 120 for config in configs))
        state = [call for call in mqtt.publish.call_args_list if call.args[0].endswith("/state")][0]
        self.assertFalse(state.kwargs["retain"])
        payload = json.loads(state.args[1])
        self.assertEqual(payload["estimated_start_display"], "13/11/2026 01.59")
        self.assertEqual(payload["estimated_start"], self.snapshot()["estimated_start"])

    def test_display_format_uses_24_hour_local_time_and_summer_time(self):
        snapshot = {"estimated_start": "2026-07-12T22:05:00+00:00",
                    "estimated_complete": "2026-11-13T15:04:00+00:00", "latest_completion": None}
        display = schedule_display_values(snapshot)
        self.assertEqual(display["estimated_start_display"], "13/07/2026 00.05")
        self.assertEqual(display["estimated_complete_display"], "13/11/2026 16.04")
        self.assertIsNone(display["latest_completion_display"])

    def test_overdue_waiting_session_does_not_predict_a_past_finish(self):
        self.assertIsNone(self.snapshot(datetime(2026, 11, 13, 6, tzinfo=timezone.utc))
                          ["estimated_complete"])

    def test_charging_uses_current_time_and_current_soc(self):
        self.charge.update(state="charging", soc={"percentage": 100})
        self.assertEqual(self.snapshot()["estimated_complete"], self.now.isoformat())

    def test_redirect_requests_a_new_session_without_following_login(self):
        client = MontaClient()
        client.session = Mock(spec=requests.Session)
        client.session.request.return_value.status_code = 302
        with self.assertRaisesRegex(MontaReadError, "Hub session rejected"):
            client.request("GET", "https://hub.monta.app/api/gateway/api/v1/charges/1")
        self.assertFalse(client.session.request.call_args.kwargs["allow_redirects"])


if __name__ == "__main__":
    unittest.main()
