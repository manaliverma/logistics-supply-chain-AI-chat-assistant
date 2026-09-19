"""Apply the Phase 2 SQL security setup without storing the password in SQL."""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def main() -> None:
    password = os.getenv("AGENT_FDE_RO_PASSWORD")
    if not password:
        raise RuntimeError("Missing AGENT_FDE_RO_PASSWORD in .env")

    sql_path = ROOT / "scripts/setup_security_and_view.sql"
    sql = sql_path.read_text(encoding="utf-8")
    escaped_password = password.replace("'", "''")
    sql = sql.replace("$(AGENT_FDE_RO_PASSWORD)", escaped_password)
    statements = [
        statement.strip()
        for statement in re.split(r"^\s*GO\s*$", sql, flags=re.MULTILINE | re.IGNORECASE)
        if statement.strip()
    ]

    connection_url = URL.create(
        "mssql+pymssql",
        username=os.environ["MSSQL_USER"],
        password=os.environ["MSSQL_PASSWORD"],
        host=os.getenv("MSSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MSSQL_PORT", "1433")),
        database="master",
    )
    engine = create_engine(connection_url, pool_pre_ping=True)
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
    print("Applied Phase 2 SQL security setup.")


if __name__ == "__main__":
    main()
