import json
import os
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from src import agent_tools


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class AgentToolsTests(unittest.TestCase):
    def test_weather_adds_wmo_description(self):
        payload = {
            "current": {"weather_code": 61},
            "hourly": {"time": ["2026-09-20T00:00"]},
        }
        with patch("src.agent_tools.urlopen", return_value=FakeResponse(payload)):
            result = agent_tools.get_weather.invoke(
                {"latitude": 33.77, "longitude": -118.19}
            )

        self.assertEqual(result["current"]["weather_code_description"], "slight rain")

    def test_weather_failure_is_structured_and_retryable(self):
        with patch(
            "src.agent_tools.urlopen",
            side_effect=URLError("offline"),
        ):
            result = agent_tools.get_weather.invoke(
                {"latitude": 33.77, "longitude": -118.19}
            )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["provider"], "Open-Meteo")
        self.assertTrue(result["retryable"])
        self.assertNotIn("offline", result["error"])

    def test_route_success_marks_result_as_not_live_traffic(self):
        payload = {
            "code": "Ok",
            "routes": [{"distance": 1000, "duration": 120}],
            "waypoints": [],
        }
        with patch("src.agent_tools.urlopen", return_value=FakeResponse(payload)):
            result = agent_tools.get_route.invoke(
                {
                    "origin_latitude": 33.77,
                    "origin_longitude": -118.19,
                    "destination_latitude": 34.05,
                    "destination_longitude": -118.25,
                }
            )

        self.assertEqual(result["provider"], "OSRM/OpenStreetMap")
        self.assertFalse(result["live_traffic"])
        self.assertEqual(len(result["routes"]), 1)

    def test_route_provider_error_is_not_retryable(self):
        payload = {"code": "NoRoute"}
        with patch("src.agent_tools.urlopen", return_value=FakeResponse(payload)):
            result = agent_tools.get_route.invoke(
                {
                    "origin_latitude": 33.77,
                    "origin_longitude": -118.19,
                    "destination_latitude": 34.05,
                    "destination_longitude": -118.25,
                }
            )

        self.assertEqual(result["status"], "error")
        self.assertFalse(result["retryable"])
        self.assertIn("NoRoute", result["error"])

    def test_validation_rejects_bad_coordinates_and_limits(self):
        with self.assertRaises(ValueError):
            agent_tools.get_weather.invoke({"latitude": 91, "longitude": 0})
        with self.assertRaises(ValueError):
            agent_tools.get_route.invoke(
                {
                    "origin_latitude": 0,
                    "origin_longitude": 0,
                    "destination_latitude": 0,
                    "destination_longitude": 181,
                }
            )
        with self.assertRaises(ValueError):
            agent_tools.query_telemetry.invoke({"limit": 0})

    def test_incident_approval_and_audit_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "operations.sqlite3")
            with patch.object(agent_tools, "OPERATIONS_DB", agent_tools.Path(database)):
                incident = agent_tools.record_incident.invoke(
                    {
                        "shipment_id": "TEST-1",
                        "decision": {
                            "severity": "critical",
                            "reasons": ["temperature breach"],
                        },
                    }
                )
                approval = agent_tools.request_human_approval.invoke(
                    {
                        "incident_id": incident["incident_id"],
                        "action": "hold shipment",
                    }
                )
                statuses = agent_tools.get_incident_status.invoke(
                    {"incident_id": incident["incident_id"]}
                )
                audit = agent_tools.write_audit_event.invoke(
                    {
                        "event_type": "incident_detected",
                        "request_id": "REQ-TEST",
                        "payload": {
                            "incident_id": incident["incident_id"],
                            "approval_id": approval["approval_id"],
                        },
                    }
                )
                events = agent_tools.get_audit_events.invoke(
                    {"request_id": "REQ-TEST"}
                )

        self.assertEqual(incident["status"], "open")
        self.assertEqual(approval["status"], "pending")
        self.assertEqual(len(statuses), 1)
        self.assertTrue(audit["event_id"].startswith("AUD-"))
        self.assertEqual(audit["request_id"], "REQ-TEST")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["payload"]["incident_id"], incident["incident_id"])

    def test_audit_rejects_secret_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "operations.sqlite3")
            with patch.object(agent_tools, "OPERATIONS_DB", agent_tools.Path(database)):
                with self.assertRaises(ValueError):
                    agent_tools.write_audit_event.invoke(
                        {
                            "event_type": "bad_event",
                            "payload": {"api_key": "should-not-be-stored"},
                        }
                    )

    def test_audit_rejects_nested_secret_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "operations.sqlite3")
            with patch.object(agent_tools, "OPERATIONS_DB", agent_tools.Path(database)):
                with self.assertRaises(ValueError):
                    agent_tools.write_audit_event.invoke(
                        {
                            "event_type": "bad_event",
                            "payload": {"evidence": [{"credentials": {"token": "x"}}]},
                        }
                    )

    def test_audit_uses_active_request_context_when_not_provided(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "operations.sqlite3")
            with patch.object(agent_tools, "OPERATIONS_DB", agent_tools.Path(database)):
                token = agent_tools.ACTIVE_REQUEST_ID.set("REQ-CONTEXT")
                try:
                    result = agent_tools.write_audit_event.invoke(
                        {
                            "event_type": "final_assessment",
                            "payload": {"status": "critical"},
                        }
                    )
                finally:
                    agent_tools.ACTIVE_REQUEST_ID.reset(token)

        self.assertEqual(result["request_id"], "REQ-CONTEXT")

    def test_record_incident_normalizes_status(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "operations.sqlite3")
            with patch.object(agent_tools, "OPERATIONS_DB", agent_tools.Path(database)):
                result = agent_tools.record_incident.invoke(
                    {
                        "shipment_id": " TEST-1 ",
                        "decision": {"severity": "critical"},
                        "status": " Open ",
                    }
                )

        self.assertEqual(result["shipment_id"], "TEST-1")
        self.assertEqual(result["status"], "open")


if __name__ == "__main__":
    unittest.main()
