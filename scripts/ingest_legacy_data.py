"""Load the selected logistics fields into the legacy SQL Server table."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


LEGACY_MAPPING = {
    "timestamp": "TS_UTC",
    "vehicle_gps_latitude": "V_LAT",
    "vehicle_gps_longitude": "V_LON",
    "iot_temperature": "IOT_TEMP_VAL_C",
    "cargo_condition_status": "CGO_COND_CD",
    "risk_classification": "RISK_CLS_TXT",
    "delay_probability": "DELAY_PROB_DEC",
    "port_congestion_level": "PRT_CNG_LVL",
    "route_risk_level": "RT_RSK_IDX",
}


def setting(*names: str, default: str | None = None) -> str:
    """Return the first configured environment value from the supplied names."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    if default is not None:
        return default
    raise RuntimeError(f"Missing required setting: {' or '.join(names)}")


def build_engine():
    """Create the administrator SQLAlchemy engine used for initial loading."""
    host = setting("SQL_SERVER_HOST", "MSSQL_HOST", default="127.0.0.1")
    port = setting("SQL_SERVER_PORT", "MSSQL_PORT", default="1433")
    user = setting("SQL_ADMIN_USER", "MSSQL_USER", default="sa")
    password = setting("SQL_ADMIN_PASSWORD", "MSSQL_PASSWORD")

    connection_url = URL.create(
        "mssql+pymssql",
        username=user,
        password=password,
        host=host,
        port=int(port),
        database="master",
    )
    return create_engine(connection_url, pool_pre_ping=True)


def wait_for_sql_server(engine, attempts: int = 30) -> None:
    """Poll SQL Server until it accepts a simple connectivity query."""
    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except Exception as error:
            if attempt == attempts:
                raise RuntimeError("SQL Server did not become ready") from error
            time.sleep(2)


def main() -> int:
    """Map and load the raw CSV fields into the legacy SQL table."""
    data_path = PROJECT_ROOT / setting(
        "DATA_FILE",
        default="data/raw/dynamic_supply_chain_logistics_dataset.csv",
    )
    table_name = setting("MSSQL_TABLE", default="TBL_SC_FLEET_HIST_RAW")
    if not data_path.is_file():
        raise FileNotFoundError(f"Dataset not found: {data_path}")

    print(f"Loading CSV from {data_path}...")
    dataframe = pd.read_csv(data_path)
    missing_columns = sorted(set(LEGACY_MAPPING) - set(dataframe.columns))
    if missing_columns:
        raise ValueError(f"Dataset is missing columns: {', '.join(missing_columns)}")

    legacy_dataframe = dataframe[list(LEGACY_MAPPING)].rename(
        columns=LEGACY_MAPPING
    )
    legacy_dataframe["SYS_INGEST_FLAG"] = "Y"

    print("Connecting to legacy MSSQL Database...")
    engine = build_engine()
    wait_for_sql_server(engine)

    print(f"Ingesting into dbo.{table_name}...")
    legacy_dataframe.to_sql(
        table_name,
        engine,
        if_exists="replace",
        index=False,
        schema="dbo",
        chunksize=1000,
    )

    with engine.connect() as connection:
        loaded_rows = connection.execute(
            text(f"SELECT COUNT(*) FROM [dbo].[{table_name}]")
        ).scalar_one()

    print(f"Legacy data ingestion complete: {loaded_rows:,} rows loaded.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Ingestion failed: {error}", file=sys.stderr)
        raise
