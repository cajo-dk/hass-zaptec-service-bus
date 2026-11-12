import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import zaptec_charge_monitor as monitor


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.cache = {}
        self.discovered = set()

    def send(self, state_id, value, timestamp="2026-11-12T10:00:00Z"):
        body = json.dumps({"ChargerId": "charger-1", "DeviceId": "ZAP123",
                           "StateId": state_id, "ValueAsString": value,
                           "Timestamp": timestamp}).encode()
        monitor.process_message(Mock(body=[body]), self.client, self.discovered,
                                self.cache, "homeassistant", "zaptec", True, "ERROR")
        return json.loads(self.client.publish.call_args.args[1])

    def test_schedule_payload_is_preserved_as_attribute(self):
        value = {"vendor_specific": [1, 2, 3]}
        result = self.send(762, json.dumps(value))
        self.assertEqual(result["time_schedule"], value)
        self.assertNotIn("next_scheduled_start", result)
        configs = [json.loads(c.args[1]) for c in self.client.publish.call_args_list
                   if c.args[0].endswith("/config")]
        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0]["json_attributes_topic"],
                         "zaptec/chargers/charger_1/state")

    def test_cancellation_clears_retained_schedule(self):
        self.send(763, "opaque event data")
        self.assertIsNone(self.send(763, None, "2026-11-12T11:00:00Z")
                          ["next_schedule_event"])
        self.assertIsNone(self.send(763, "stale", "2026-11-12T10:00:00Z")
                          ["next_schedule_event"])

    def test_stale_schedule_does_not_replace_newer_data(self):
        self.send(762, "new", "2026-11-12T11:00:00Z")
        self.assertEqual(self.send(762, "old")["time_schedule"], "new")

    def test_empty_string_clears_schedule(self):
        self.send(762, "old")
        self.assertIsNone(self.send(762, "")["time_schedule"])

    def test_charge_state_and_zeroing_still_work(self):
        self.send(710, "3")
        self.assertEqual(self.send(513, "4000")["total_charge_power"], 4000)
        result = self.send(710, "5", "2026-11-12T11:00:00Z")
        self.assertEqual(result["state"], "connected_finished_idle")
        self.assertEqual(result["total_charge_power"], 0)

    def test_container_runtime_matches_root_runtime(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual((root / "zaptec_charge_monitor.py").read_bytes(),
                         (root / "zaptec_service_bus/zaptec_charge_monitor.py").read_bytes())
        self.assertEqual((root / "requirements.txt").read_bytes(),
                         (root / "zaptec_service_bus/requirements.txt").read_bytes())
        self.assertEqual((root / "monta_charge_monitor.py").read_bytes(),
                         (root / "zaptec_service_bus/monta_charge_monitor.py").read_bytes())

    def test_mqtt_rejection_stops_startup_before_service_bus_receives(self):
        client = Mock()
        reason = Mock(is_failure=True)
        reason.__str__ = Mock(return_value="Not authorized")
        client.loop_start.side_effect = lambda: client.on_connect(client, None, None, reason, None)
        with patch.object(monitor.mqtt, "Client", return_value=client):
            with patch.dict("os.environ", {"MQTT_HOST": "localhost"}):
                with self.assertRaisesRegex(ValueError, "MQTT connection failed: Not authorized"):
                    monitor.create_mqtt_client()
        client.disconnect.assert_called_once()
        client.loop_stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
