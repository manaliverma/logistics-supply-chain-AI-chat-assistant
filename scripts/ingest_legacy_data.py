"""Load the logistics CSV into SQL Server."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def setting(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if not value:
        raise RuntimeError(f"Missing required setting: {name}")
    return value


def build_engine():
    connection_url = URL.create(
        "mssql+pymssql",
        username=setting("MSSQL_USER", "sa"),
        password=setting("MSSQL_PASSWORD"),
        host=setting("MSSQL_HOST", "127.0.0.1"),
        port=int(setting("MSSQL_PORT", "1433")),
        database=setting("MSSQL_DATABASE", "master"),
    )
    return create_engine(connection_url, pool_pre_ping=True)


def wait_for_sql_server(engine, attempts: int = 30) -> None:
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
    data_file = ROOT / setting(
        "DATA_FILE", "data/raw/dynamic_supply_chain_logistics_dataset.csv"
    )
    table_name = setting("MSSQL_TABLE", "TBL_SC_FLEET_HIST_RAW")
    if not data_file.is_file():
        raise FileNotFoundError(f"Dataset not found: {data_file}")

    dataframe = pd.read_csv(data_file)
    if dataframe.empty:
        raise ValueError(f"Dataset is empty: {data_file}")

    engine = build_engine()
    wait_for_sql_server(engine)

    table_exists = inspect(engine).has_table(table_name, schema="dbo")
    if table_exists:
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE [dbo].[{table_name}]"))

    dataframe.to_sql(
        table_name,
        engine,
        schema="dbo",
        if_exists="replace",
        index=False,
        chunksize=1000,
        method=None,
    )

    with engine.connect() as connection:
        loaded_rows = connection.execute(
            text(f"SELECT COUNT(*) FROM [dbo].[{table_name}]")
        ).scalar_one()

    print(f"Loaded {loaded_rows:,} rows into dbo.{table_name}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Ingestion failed: {error}", file=sys.stderr)
        raise
