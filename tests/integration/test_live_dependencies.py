"""Opt-in integration checks for configured external and local services."""

from __future__ import annotations

import os
import unittest

from src import agent_tools
from src.orchestrator import run_request


LIVE = os.getenv("RUN_INTEGRATION_TESTS") == "1"


@unittest.skipUnless(LIVE, "Set RUN_INTEGRATION_TESTS=1 to run live checks")
class LiveDependencyTests(unittest.TestCase):
    def test_sql_server_curated_view(self):
        rows = agent_tools.query_telemetry.invoke({"limit": 1})
        self.assertIsInstance(rows, list)

    def test_pinecone_retrieval(self):
        result = agent_tools.search_sop_compliance.invoke(
            {"question": "What is the chilled cold-chain maximum temperature?"}
        )
        self.assertIn("matches", result)

    def test_weather_provider(self):
        result = agent_tools.get_weather.invoke(
            {"latitude": 34.05, "longitude": -118.25}
        )
        self.assertNotEqual(result.get("status"), "error")
        self.assertIn("current", result)

    def test_routing_provider(self):
        result = agent_tools.get_route.invoke(
            {
                "origin_latitude": 34.05,
                "origin_longitude": -118.25,
                "destination_latitude": 34.06,
                "destination_longitude": -118.24,
            }
        )
        self.assertNotEqual(result.get("status"), "error")
        self.assertIn("routes", result)

    def test_audit_database(self):
        result = agent_tools.write_audit_event.invoke(
            {
                "event_type": "integration_test",
                "payload": {"status": "ok"},
                "request_id": "REQ-INTEGRATION",
            }
        )
        self.assertTrue(result["event_id"].startswith("AUD-"))

    def test_llm_tool_calling_smoke(self):
        result = run_request(
            "Check shipment compliance for US-FC-00032065.",
            request_id="REQ-LLM-INTEGRATION",
        )
        self.assertIn("messages", result)
        self.assertTrue(result["messages"])
