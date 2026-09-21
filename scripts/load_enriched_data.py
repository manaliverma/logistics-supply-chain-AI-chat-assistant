"""Load the synthetic enriched logistics dataset into SQL Server."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def main() -> None:
    """Replace the SQL Server enriched table with the generated dataset."""
    data_path = ROOT / "data/processed/amazon_like_logistics_dataset.csv"
    if not data_path.is_file():
        raise FileNotFoundError(f"Dataset not found: {data_path}")

    connection_url = URL.create(
        "mssql+pymssql",
        username=os.environ["MSSQL_USER"],
        password=os.environ["MSSQL_PASSWORD"],
        host=os.getenv("MSSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MSSQL_PORT", "1433")),
        database=os.getenv("MSSQL_DATABASE", "master"),
    )
    dataframe = pd.read_csv(data_path)
    engine = create_engine(connection_url, pool_pre_ping=True)
    dataframe.to_sql(
        "TBL_SC_FLEET_ENRICHED",
        engine,
        schema="dbo",
        if_exists="replace",
        index=False,
        chunksize=1000,
    )
    print(
        f"Loaded {len(dataframe):,} rows into "
        "dbo.TBL_SC_FLEET_ENRICHED"
    )


if __name__ == "__main__":
    main()
