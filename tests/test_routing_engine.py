import unittest

import pandas as pd

from scripts.routing_engine import evaluate_shipment


def shipment(**overrides):
    values = {
        "cold_chain_required": True,
        "iot_temperature": 2.0,
        "max_temperature_c": 8.0,
        "exposure_duration_minutes": 10,
        "max_exposure_minutes": 30,
        "reefer_power_available": True,
        "port_congestion_level": 1.0,
        "road_closure": False,
        "weather_status": "clear",
        "depot_capacity_pct": 60.0,
        "risk_classification": "Low Risk",
        "delay_probability": 0.1,
    }
    values.update(overrides)
    return pd.Series(values)


class RoutingEngineTests(unittest.TestCase):
    def test_normal_shipment_has_no_trigger(self):
        decision = evaluate_shipment(shipment())

        self.assertEqual(decision.severity, "normal")
        self.assertEqual(decision.next_update_minutes, 60)
        self.assertIn("No deterministic SOP trigger", decision.reasons[0])

    def test_temperature_breach_is_critical(self):
        decision = evaluate_shipment(shipment(iot_temperature=10.0))

        self.assertEqual(decision.severity, "critical")
        self.assertTrue(any("Temperature exceeds" in reason for reason in decision.reasons))
        self.assertIn("Quality Owner", decision.escalate_to)

    def test_port_congestion_thresholds(self):
        elevated = evaluate_shipment(shipment(port_congestion_level=4.0))
        critical = evaluate_shipment(shipment(port_congestion_level=8.0))

        self.assertEqual(elevated.severity, "elevated")
        self.assertEqual(critical.severity, "critical")
        self.assertIn("Dispatcher", critical.escalate_to)

    def test_multiple_triggers_are_deduplicated(self):
        decision = evaluate_shipment(
            shipment(
                iot_temperature=10.0,
                exposure_duration_minutes=60,
                reefer_power_available=False,
                road_closure=True,
            )
        )

        self.assertEqual(decision.severity, "critical")
        self.assertEqual(len(decision.actions), len(set(decision.actions)))
        self.assertEqual(len(decision.escalate_to), len(set(decision.escalate_to)))


if __name__ == "__main__":
    unittest.main()
