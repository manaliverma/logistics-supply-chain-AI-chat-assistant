"""Create synthetic Amazon-like logistics fields for local learning."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/raw/dynamic_supply_chain_logistics_dataset.csv"
OUTPUT = ROOT / "data/processed/amazon_like_logistics_dataset.csv"

PRODUCT_PROFILES = [
    {
        "product_type": "chilled seafood",
        "product_category": "perishable_food",
        "min_temperature_c": 0.0,
        "max_temperature_c": 4.0,
        "max_exposure_minutes": 60,
        "cold_chain_required": True,
    },
    {
        "product_type": "fresh produce",
        "product_category": "perishable_food",
        "min_temperature_c": 1.0,
        "max_temperature_c": 5.0,
        "max_exposure_minutes": 90,
        "cold_chain_required": True,
    },
    {
        "product_type": "frozen food",
        "product_category": "frozen_food",
        "min_temperature_c": -25.0,
        "max_temperature_c": -18.0,
        "max_exposure_minutes": 45,
        "cold_chain_required": True,
    },
    {
        "product_type": "pharmaceutical",
        "product_category": "healthcare",
        "min_temperature_c": 2.0,
        "max_temperature_c": 8.0,
        "max_exposure_minutes": 30,
        "cold_chain_required": True,
    },
    {
        "product_type": "consumer electronics",
        "product_category": "general_merchandise",
        "min_temperature_c": 5.0,
        "max_temperature_c": 35.0,
        "max_exposure_minutes": 240,
        "cold_chain_required": False,
    },
    {
        "product_type": "apparel",
        "product_category": "general_merchandise",
        "min_temperature_c": 5.0,
        "max_temperature_c": 40.0,
        "max_exposure_minutes": 360,
        "cold_chain_required": False,
    },
]

WEATHER_BY_MONTH = {
    1: "winter_storm",
    2: "winter_storm",
    3: "heavy_rain",
    4: "heavy_rain",
    5: "heat_spike",
    6: "heat_wave",
    7: "heat_wave",
    8: "heat_wave",
    9: "wildfire_smoke",
    10: "heavy_rain",
    11: "flood_watch",
    12: "winter_storm",
}


def stable_number(value: str, modulo: int) -> int:
    """Return a deterministic bounded value for reproducible synthetic fields."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % modulo


def main() -> None:
    """Generate the enriched synthetic shipment dataset from the raw CSV."""
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Dataset not found: {SOURCE}")

    dataframe = pd.read_csv(SOURCE)
    timestamps = pd.to_datetime(dataframe["timestamp"])
    enriched = dataframe.copy()

    profiles = [
        PRODUCT_PROFILES[index % len(PRODUCT_PROFILES)]
        for index in range(len(enriched))
    ]
    enriched["shipment_id"] = [
        f"US-FC-{index:08d}" for index in range(1, len(enriched) + 1)
    ]
    enriched["fulfillment_center"] = [
        ["LAX9", "ONT8", "PHX6", "DFW7", "EWR4"][index % 5]
        for index in range(len(enriched))
    ]
    enriched["destination_region"] = [
        ["Southern California", "Pacific Northwest", "Southwest", "Mountain West"][
            index % 4
        ]
        for index in range(len(enriched))
    ]
    enriched["product_type"] = [profile["product_type"] for profile in profiles]
    enriched["product_category"] = [
        profile["product_category"] for profile in profiles
    ]
    enriched["min_temperature_c"] = [
        profile["min_temperature_c"] for profile in profiles
    ]
    enriched["max_temperature_c"] = [
        profile["max_temperature_c"] for profile in profiles
    ]
    enriched["max_exposure_minutes"] = [
        profile["max_exposure_minutes"] for profile in profiles
    ]
    enriched["cold_chain_required"] = [
        profile["cold_chain_required"] for profile in profiles
    ]
    enriched["weather_status"] = [
        WEATHER_BY_MONTH[timestamp.month] for timestamp in timestamps
    ]
    enriched["ambient_temperature_c"] = [
        round(
            12
            + timestamp.month * 1.8
            + stable_number(f"ambient-{index}", 120) / 10,
            1,
        )
        for index, timestamp in enumerate(timestamps)
    ]
    enriched["road_closure"] = [
        weather in {"flood_watch", "winter_storm"}
        and stable_number(f"road-{index}", 10) == 0
        for index, weather in enumerate(enriched["weather_status"])
    ]
    enriched["exposure_duration_minutes"] = [
        int(
            10
            + stable_number(f"exposure-{index}", 260)
            + (45 if weather in {"heat_wave", "heat_spike"} else 0)
        )
        for index, weather in enumerate(enriched["weather_status"])
    ]
    enriched["depot_capacity_pct"] = [
        55 + stable_number(f"depot-{index}", 46) for index in range(len(enriched))
    ]
    enriched["reefer_power_available"] = [
        not (
            weather in {"heat_wave", "heat_spike", "power_outage"}
            and stable_number(f"reefer-{index}", 12) == 0
        )
        for index, weather in enumerate(enriched["weather_status"])
    ]
    enriched["weather_related_disruption"] = [
        weather in {"heat_wave", "heat_spike", "flood_watch", "winter_storm", "wildfire_smoke"}
        for weather in enriched["weather_status"]
    ]
    enriched["synthetic_data_notice"] = "Synthetic learning data; not Amazon production data"

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_csv(OUTPUT, index=False)
    print(f"Created {len(enriched):,} enriched rows at {OUTPUT}")


if __name__ == "__main__":
    main()
