"""Expose local operational metrics in Prometheus text format."""

from __future__ import annotations

import math
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
METRICS_DB = Path(
    os.getenv("METRICS_DB", str(ROOT / "data/cache/agent_operations.sqlite3"))
)
PORT = int(os.getenv("METRICS_EXPORTER_PORT", "9108"))


def _metric_name(name: str) -> str:
    return "logistics_" + "".join(
        character if character.isalnum() else "_" for character in name.lower()
    ).strip("_")


def _percentile(values: list[float], fraction: float) -> float:
    values = sorted(values)
    index = min(len(values) - 1, round((len(values) - 1) * fraction))
    return values[index]


def render_metrics() -> str:
    """Render counters and latency quantiles from the local metrics database."""
    if not METRICS_DB.exists():
        return "# HELP logistics_metrics_database_available Metrics database status.\nlogistics_metrics_database_available 0\n"
    try:
        with sqlite3.connect(METRICS_DB) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT metric_name, value
                FROM operational_metrics
                WHERE recorded_at >= datetime('now', '-1 hour')
                """
            ).fetchall()
    except sqlite3.Error:
        return "# HELP logistics_metrics_database_available Metrics database status.\nlogistics_metrics_database_available 0\n"

    grouped: dict[str, list[float]] = {}
    for row in rows:
        grouped.setdefault(row["metric_name"], []).append(float(row["value"]))

    lines = [
        "# HELP logistics_metrics_database_available Metrics database status.",
        "# TYPE logistics_metrics_database_available gauge",
        "logistics_metrics_database_available 1",
    ]
    for name, values in sorted(grouped.items()):
        exported = _metric_name(name)
        total = sum(values)
        lines.extend(
            [
                f"# TYPE {exported}_total counter",
                f"{exported}_total {total}",
            ]
        )
        if name.endswith("_latency_ms") or name == "request_latency_ms":
            lines.extend(
                [
                    f"# TYPE {exported}_quantile gauge",
                    f'{exported}_quantile{{quantile="0.5"}} {_percentile(values, 0.50)}',
                    f'{exported}_quantile{{quantile="0.9"}} {_percentile(values, 0.90)}',
                    f'{exported}_quantile{{quantile="0.95"}} {_percentile(values, 0.95)}',
                ]
            )
    return "\n".join(lines) + "\n"


class MetricsHandler(BaseHTTPRequestHandler):
    """Serve Prometheus metrics and a health endpoint."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
        elif self.path == "/metrics":
            body = render_metrics().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
        else:
            body = b"not found\n"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    """Start the local Prometheus metrics exporter."""
    ThreadingHTTPServer(("0.0.0.0", PORT), MetricsHandler).serve_forever()


if __name__ == "__main__":
    main()
