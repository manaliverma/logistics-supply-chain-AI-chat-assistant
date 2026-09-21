"""Apply deterministic logistics routing and escalation rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class RoutingDecision:
    severity: str
    actions: tuple[str, ...]
    reasons: tuple[str, ...]
    escalate_to: tuple[str, ...]
    next_update_minutes: int

    def as_dict(self) -> dict[str, Any]:
        """Serialize the immutable routing decision for tools and JSON output."""
        return {
            "severity": self.severity,
            "actions": list(self.actions),
            "reasons": list(self.reasons),
            "escalate_to": list(self.escalate_to),
            "next_update_minutes": self.next_update_minutes,
        }


def evaluate_shipment(shipment: pd.Series) -> RoutingDecision:
    """Evaluate one enriched shipment without inventing missing inputs."""
    actions: list[str] = []
    reasons: list[str] = []
    escalation: list[str] = []
    severity = "normal"
    next_update = 60

    def critical(reason: str, action: str, minutes: int = 15) -> None:
        """Register a critical trigger and shorten the update interval."""
        nonlocal severity, next_update
        severity = "critical"
        reasons.append(reason)
        actions.append(action)
        next_update = min(next_update, minutes)

    product_is_cold_chain = bool(shipment["cold_chain_required"])
    temperature_breach = (
        product_is_cold_chain
        and float(shipment["iot_temperature"])
        > float(shipment["max_temperature_c"])
    )
    exposure_breach = (
        product_is_cold_chain
        and float(shipment["exposure_duration_minutes"])
        > float(shipment["max_exposure_minutes"])
    )
    power_failure = product_is_cold_chain and not bool(
        shipment["reefer_power_available"]
    )

    if temperature_breach:
        critical(
            "Temperature exceeds the product-specific maximum.",
            "Move shipment to validated cold storage and hold disposition.",
        )
        escalation.extend(["Area Manager", "Quality Owner", "Tier 2 Logistics Manager"])
    if exposure_breach:
        critical(
            "Temperature exposure exceeds the product-specific time limit.",
            "Record exposure duration and obtain quality disposition.",
        )
        escalation.extend(["Area Manager", "Quality Owner"])
    if power_failure:
        critical(
            "Reefer power is unavailable for cold-chain cargo.",
            "Restore power or transfer the shipment to a powered reefer.",
        )
        escalation.extend(["Area Manager", "Carrier"])

    port_level = float(shipment["port_congestion_level"])
    if port_level > 7.0:
        critical(
            "Port congestion exceeds the critical threshold.",
            "Suspend standard routing and divert to the Inland Empire Overflow Depot.",
        )
        escalation.append("Dispatcher")
    elif port_level > 3.0:
        severity = max(severity, "elevated", key=("normal", "elevated", "critical").index)
        reasons.append("Port congestion is elevated.")
        actions.append("Review alternate appointments and routes.")
        next_update = min(next_update, 30)

    if bool(shipment["road_closure"]):
        critical(
            "The assigned route has a road closure.",
            "Stop dispatch through the affected route and confirm an alternate route.",
        )
        escalation.append("Area Manager")

    weather = str(shipment["weather_status"])
    if weather in {"heat_wave", "heat_spike", "flood_watch", "winter_storm", "wildfire_smoke"}:
        reasons.append(f"Weather disruption detected: {weather}.")
        actions.append("Verify route safety, reefer power, ETA, and receiving capacity.")
        next_update = min(next_update, 30)
        if severity == "normal":
            severity = "elevated"

    if float(shipment["depot_capacity_pct"]) > 90.0:
        reasons.append("Overflow depot capacity exceeds 90%.")
        actions.append("Do not route additional freight there; confirm alternate capacity.")
        next_update = min(next_update, 30)
        if severity == "normal":
            severity = "elevated"

    if (
        str(shipment["risk_classification"]) == "High Risk"
        and float(shipment["delay_probability"]) > 0.65
    ):
        reasons.append("High-risk shipment exceeds the delay escalation threshold.")
        actions.append("Create a recovery plan and prioritize downstream appointments.")
        escalation.append("Tier 2 Logistics Manager")
        next_update = min(next_update, 15)
        if severity == "normal":
            severity = "elevated"

    if not actions:
        actions.append("Continue standard routing and monitor the shipment.")
        reasons.append("No deterministic SOP trigger was detected.")

    return RoutingDecision(
        severity=severity,
        actions=tuple(dict.fromkeys(actions)),
        reasons=tuple(dict.fromkeys(reasons)),
        escalate_to=tuple(dict.fromkeys(escalation)),
        next_update_minutes=next_update,
    )


def evaluate_dataset(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Return one routing decision per shipment."""
    decisions = dataframe.apply(evaluate_shipment, axis=1)
    return pd.DataFrame([decision.as_dict() for decision in decisions], index=dataframe.index)


def main() -> None:
    dataframe = pd.read_csv("data/processed/amazon_like_logistics_dataset.csv")
    decisions = evaluate_dataset(dataframe)
    output = pd.concat([dataframe[["shipment_id"]], decisions], axis=1)
    print(output.head(10).to_json(orient="records", indent=2))


if __name__ == "__main__":
    main()
