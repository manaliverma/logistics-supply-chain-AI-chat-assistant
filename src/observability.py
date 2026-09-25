"""Metrics, failure classification, and alert evaluation for operations."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
METRICS_DB = ROOT / "data/cache/agent_operations.sqlite3"


def now_utc() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def classify_failure(error: BaseException) -> str:
    """Classify failures for routing, dashboards, and alert policies."""
    name = type(error).__name__.lower()
    message = str(error).lower()
    if "quota" in name or "resource_exhausted" in message or "rate limit" in message:
        return "model_quota_failure"
    if "permission" in name or "denied" in message or "forbidden" in message:
        return "database_permission_failure"
    if "missing" in message or "api_key" in message or "password" in message:
        return "missing_secret"
    if "config" in name or "invalid" in message:
        return "invalid_configuration"
    if "connection" in name or "timeout" in name or "unavailable" in message:
        return "recoverable_dependency_failure"
    return "unknown_failure"


def _connection() -> sqlite3.Connection:
    METRICS_DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(METRICS_DB)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS operational_metrics (
            metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL,
            value REAL NOT NULL,
            request_id TEXT,
            recorded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS operational_alerts (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_name TEXT NOT NULL,
            severity TEXT NOT NULL,
            details_json TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            resolved_at TEXT
        );
        """
    )
    return connection


def record_metric(
    metric_name: str,
    value: float = 1,
    *,
    request_id: str | None = None,
) -> None:
    """Persist one numeric metric without storing sensitive request content."""
    if not metric_name.strip():
        raise ValueError("metric_name must not be empty")
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO operational_metrics
                (metric_name, value, request_id, recorded_at)
            VALUES (?, ?, ?, ?)
            """,
            (metric_name.strip(), float(value), request_id, now_utc()),
        )
        connection.commit()


def record_failure(error: BaseException, *, request_id: str | None = None) -> str:
    """Record a classified failure and return its operational category."""
    category = classify_failure(error)
    record_metric(f"failure.{category}", request_id=request_id)
    return category


def evaluate_alerts(*, request_id: str | None = None) -> list[dict[str, Any]]:
    """Evaluate conservative local thresholds and persist newly triggered alerts."""
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT metric_name, value
            FROM operational_metrics
            WHERE recorded_at >= datetime('now', '-1 hour')
            """
        ).fetchall()
        totals: dict[str, float] = {}
        for row in rows:
            totals[row["metric_name"]] = totals.get(row["metric_name"], 0) + row["value"]

        candidates: list[tuple[str, str, dict[str, Any]]] = []
        if totals.get("failure.model_quota_failure", 0) > 0:
            candidates.append(
                ("model_quota_exhausted", "high", {"count": totals["failure.model_quota_failure"]})
            )
        if totals.get("failure.database_permission_failure", 0) > 0:
            candidates.append(
                ("database_permission_failure", "critical", {"count": totals["failure.database_permission_failure"]})
            )
        if totals.get("failure.recoverable_dependency_failure", 0) >= 3:
            candidates.append(
                ("dependency_failure_rate_high", "high", {"count": totals["failure.recoverable_dependency_failure"]})
            )
        if totals.get("audit_write_failure", 0) > 0:
            candidates.append(
                ("audit_write_failure", "critical", {"count": totals["audit_write_failure"]})
            )
        triggered = []
        for name, severity, details in candidates:
            connection.execute(
                """
                INSERT INTO operational_alerts
                    (alert_name, severity, details_json, recorded_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, severity, json.dumps(details), now_utc()),
            )
            triggered.append(
                {
                    "alert_name": name,
                    "severity": severity,
                    "details": details,
                    "request_id": request_id,
                }
            )
        connection.commit()
    return triggered


def metric_summary(limit: int = 100) -> list[dict[str, Any]]:
    """Return recent metrics for a dashboard or export job."""
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT metric_name, value, request_id, recorded_at
            FROM operational_metrics
            ORDER BY metric_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def latency_percentiles(metric_name: str) -> dict[str, float | None]:
    """Return approximate p50 and p95 values for a latency metric."""
    if not metric_name.strip():
        raise ValueError("metric_name must not be empty")
    with _connection() as connection:
        values = [
            row["value"]
            for row in connection.execute(
                """
                SELECT value
                FROM operational_metrics
                WHERE metric_name = ?
                ORDER BY metric_id
                """,
                (metric_name.strip(),),
            ).fetchall()
        ]
    if not values:
        return {"p50": None, "p95": None}
    values.sort()

    def percentile(fraction: float) -> float:
        index = min(len(values) - 1, round((len(values) - 1) * fraction))
        return float(values[index])

    return {"p50": percentile(0.50), "p95": percentile(0.95)}
