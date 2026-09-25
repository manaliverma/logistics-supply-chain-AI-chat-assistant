"""Allowlisted evidence, decision, incident, and governance tools."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextvars import ContextVar
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
from dotenv import load_dotenv
from langchain_core.tools import tool
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from src.observability import record_failure, record_metric

ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
OPERATIONS_DB = ROOT / "data/cache/agent_operations.sqlite3"
WMO_WEATHER_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snow fall",
    73: "moderate snow fall",
    75: "heavy snow fall",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}
load_dotenv(ROOT / ".env")
ACTIVE_REQUEST_ID: ContextVar[str | None] = ContextVar(
    "active_request_id", default=None
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _external_api_error(provider: str, error: Exception) -> dict[str, Any]:
    """Return a safe, actionable error without exposing request details."""
    if isinstance(error, HTTPError):
        message = f"HTTP {error.code}"
    elif isinstance(error, (URLError, TimeoutError)):
        message = "connection or timeout failure"
    elif isinstance(error, json.JSONDecodeError):
        message = "invalid JSON response"
    else:
        message = type(error).__name__
    record_failure(error, request_id=ACTIVE_REQUEST_ID.get())
    record_metric(
        f"{provider.lower().replace('/', '_').replace(' ', '_')}_failure",
        request_id=ACTIVE_REQUEST_ID.get(),
    )
    return {
        "status": "error",
        "provider": provider,
        "error": message,
        "retryable": isinstance(error, (HTTPError, URLError, TimeoutError)),
    }


def _operations_connection() -> sqlite3.Connection:
    OPERATIONS_DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(OPERATIONS_DB)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS incidents (
            incident_id TEXT PRIMARY KEY,
            shipment_id TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            decision_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS approvals (
            approval_id TEXT PRIMARY KEY,
            incident_id TEXT NOT NULL,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            requested_by TEXT NOT NULL,
            reviewer TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            request_id TEXT,
            actor TEXT NOT NULL DEFAULT 'logistics-agent',
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    audit_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(audit_events)").fetchall()
    }
    if "request_id" not in audit_columns:
        connection.execute("ALTER TABLE audit_events ADD COLUMN request_id TEXT")
    if "actor" not in audit_columns:
        connection.execute(
            "ALTER TABLE audit_events ADD COLUMN actor TEXT NOT NULL DEFAULT 'logistics-agent'"
        )
    return connection


@lru_cache(maxsize=1)
def _build_vector_store():
    """Build the embedding/vector client once per application process."""
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_pinecone import PineconeVectorStore

    embeddings = HuggingFaceEmbeddings(
        model_name=MODEL_NAME,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    return PineconeVectorStore(
        index_name=os.environ["PINECONE_INDEX_NAME"],
        embedding=embeddings,
        namespace=os.getenv("PINECONE_NAMESPACE", "sop"),
        pinecone_api_key=os.environ["PINECONE_API_KEY"],
    )


@lru_cache(maxsize=1)
def _build_agent_database():
    """Build the read-only SQL engine once per application process."""
    password = os.getenv("AGENT_FDE_RO_PASSWORD")
    if not password:
        raise RuntimeError("Missing AGENT_FDE_RO_PASSWORD in .env")
    return create_engine(
        URL.create(
            "mssql+pymssql",
            username=os.getenv("AGENT_MSSQL_USER", "USR_FDE_RO"),
            password=password,
            host=os.getenv("MSSQL_HOST", "127.0.0.1"),
            port=int(os.getenv("MSSQL_PORT", "1433")),
            database=os.getenv("MSSQL_DATABASE", "master"),
        ),
        pool_pre_ping=True,
    )


def _read_telemetry(shipment_id: str | None, limit: int) -> list[dict[str, Any]]:
    started = datetime.now(timezone.utc)
    statement = text(
        """
        SELECT TOP (:limit)
            shipment_id, product_type, product_category, fulfillment_center,
            destination_region, timestamp, vehicle_gps_latitude,
            vehicle_gps_longitude, iot_temperature, max_temperature_c,
            max_exposure_minutes, exposure_duration_minutes,
            cold_chain_required, reefer_power_available, weather_status,
            road_closure, port_congestion_level, depot_capacity_pct,
            risk_classification, delay_probability, route_risk_level
        FROM FDE_VIEWS.VW_ACTIVE_FLEET
        WHERE (:shipment_id IS NULL OR shipment_id = :shipment_id)
        ORDER BY timestamp DESC
        """
    )
    with _build_agent_database().connect() as connection:
        rows = connection.execute(
            statement, {"limit": limit, "shipment_id": shipment_id}
        ).mappings()
        result = [dict(row) for row in rows]
    record_metric(
        "sql_latency_ms",
        (datetime.now(timezone.utc) - started).total_seconds() * 1000,
        request_id=ACTIVE_REQUEST_ID.get(),
    )
    return result


@tool
def search_sop_compliance(question: str, result_count: int = 4) -> dict[str, Any]:
    """Retrieve relevant SOP evidence; retrieval is not the compliance decision."""
    if not question.strip():
        raise ValueError("question must not be empty")
    if not 1 <= result_count <= 10:
        raise ValueError("result_count must be between 1 and 10")
    started = datetime.now(timezone.utc)
    documents = _build_vector_store().similarity_search(question.strip(), k=result_count)
    record_metric(
        "pinecone_latency_ms",
        (datetime.now(timezone.utc) - started).total_seconds() * 1000,
        request_id=ACTIVE_REQUEST_ID.get(),
    )
    return {
        "question": question.strip(),
        "matches": [
            {
                "content": document.page_content,
                "section": document.metadata.get("section", "unknown"),
                "source": document.metadata.get("source", "unknown"),
                "vector_id": document.metadata.get("id"),
            }
            for document in documents
        ],
    }


@tool
def query_telemetry(
    shipment_id: str | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    """Read observed shipment facts from the curated view only."""
    if shipment_id is not None and not shipment_id.strip():
        raise ValueError("shipment_id must not be blank")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    return _read_telemetry(shipment_id, limit)


@tool
def get_weather(latitude: float, longitude: float) -> dict[str, Any]:
    """Get current external weather observations from the configured provider."""
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("invalid latitude or longitude")
    base_url = os.getenv(
        "WEATHER_API_BASE_URL", "https://api.open-meteo.com/v1/forecast"
    )
    query = urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,relative_humidity_2m,weather_code,"
                "wind_speed_10m,wind_direction_10m"
            ),
            "hourly": (
                "temperature_2m,rain,snowfall,wind_speed_10m,"
                "wind_direction_10m"
            ),
            "forecast_days": 1,
            "timezone": "UTC",
        }
    )
    request = Request(
        f"{base_url}?{query}",
        headers={"Accept": "application/json", "User-Agent": "logistics-agent/1.0"},
    )
    try:
        started = datetime.now(timezone.utc)
        with urlopen(request, timeout=10) as response:
            payload = json.load(response)
        record_metric(
            "weather_api_latency_ms",
            (datetime.now(timezone.utc) - started).total_seconds() * 1000,
            request_id=ACTIVE_REQUEST_ID.get(),
        )
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        return _external_api_error("Open-Meteo", error)
    current = payload.get("current", {})
    weather_code = current.get("weather_code")
    current["weather_code_description"] = WMO_WEATHER_CODES.get(
        weather_code, "unknown weather condition"
    )
    return payload


@tool
def get_route(
    origin_latitude: float,
    origin_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
) -> dict[str, Any]:
    """Calculate a baseline driving route using the public OSRM API.

    OSRM uses OpenStreetMap road data and returns route geometry, distance,
    and estimated duration. The public service does not provide live traffic,
    live road closures, or guaranteed production availability. Treat its
    duration as a baseline estimate and combine it with trusted telemetry or
    a live traffic provider before making an operational decision.
    """
    coordinates = (
        f"{origin_longitude},{origin_latitude};"
        f"{destination_longitude},{destination_latitude}"
    )
    if not all(
        [
            -90 <= origin_latitude <= 90,
            -180 <= origin_longitude <= 180,
            -90 <= destination_latitude <= 90,
            -180 <= destination_longitude <= 180,
        ]
    ):
        raise ValueError("invalid origin or destination coordinates")

    base_url = os.getenv(
        "ROUTING_API_BASE_URL",
        "https://router.project-osrm.org/route/v1/driving",
    )
    query = urlencode({"overview": "false", "alternatives": "true", "steps": "false"})
    request = Request(
        f"{base_url}/{coordinates}?{query}",
        headers={"Accept": "application/json", "User-Agent": "logistics-agent/1.0"},
    )
    try:
        started = datetime.now(timezone.utc)
        with urlopen(request, timeout=10) as response:
            payload = json.load(response)
        record_metric(
            "routing_api_latency_ms",
            (datetime.now(timezone.utc) - started).total_seconds() * 1000,
            request_id=ACTIVE_REQUEST_ID.get(),
        )
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        return _external_api_error("OSRM/OpenStreetMap", error)
    if payload.get("code") != "Ok":
        return {
            "status": "error",
            "provider": "OSRM/OpenStreetMap",
            "error": f"routing status: {payload.get('code', 'unknown')}",
            "retryable": False,
        }
    return {
        "provider": "OSRM/OpenStreetMap",
        "live_traffic": False,
        "routes": payload.get("routes", []),
        "waypoints": payload.get("waypoints", []),
    }


@tool
def evaluate_shipment_routing(shipment_id: str) -> dict[str, Any]:
    """Apply deterministic routing rules to the latest shipment telemetry.

    Use this after retrieving a shipment from the curated telemetry view.
    The result contains the observed telemetry and the authoritative
    severity, reasons, actions, escalation owners, and next update interval.
    This tool evaluates rules only; it never changes a shipment or executes
    a route, hold, disposal, or customer-contact action.
    """
    if not shipment_id.strip():
        raise ValueError("shipment_id must not be blank")
    from scripts.routing_engine import evaluate_shipment

    rows = _read_telemetry(shipment_id.strip(), 1)
    if not rows:
        raise LookupError(f"Shipment not found: {shipment_id}")
    decision = evaluate_shipment(pd.Series(rows[0])).as_dict()
    return {"shipment_id": shipment_id.strip(), "decision": decision, "telemetry": rows[0]}


@tool
def record_incident(
    shipment_id: str, decision: dict[str, Any], status: str = "open"
) -> dict[str, str]:
    """Persist a detected compliance or routing breach for follow-up.

    ``decision`` should contain the output of
    ``evaluate_shipment_routing``. This records an incident only; it does not
    reroute, dispose of cargo, release a hold, or contact a customer.
    """
    if not shipment_id.strip():
        raise ValueError("shipment_id must not be blank")
    normalized_status = status.strip().lower()
    if normalized_status not in {"open", "acknowledged", "resolved"}:
        raise ValueError("status must be open, acknowledged, or resolved")
    incident_id = f"INC-{uuid.uuid4().hex[:12].upper()}"
    timestamp = _now()
    with _operations_connection() as connection:
        connection.execute(
            "INSERT INTO incidents VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                incident_id,
                shipment_id.strip(),
                decision.get("severity", "unknown"),
                normalized_status,
                json.dumps(decision),
                timestamp,
                timestamp,
            ),
        )
        connection.commit()
    record_metric("incident_count", request_id=ACTIVE_REQUEST_ID.get())
    return {
        "incident_id": incident_id,
        "shipment_id": shipment_id.strip(),
        "status": normalized_status,
    }


@tool
def get_incident_status(
    incident_id: str | None = None, shipment_id: str | None = None
) -> list[dict[str, Any]]:
    """Return incident records for an incident or shipment.

    Use this for follow-up after an incident is recorded. The result includes
    the stored decision and lifecycle status; it does not approve or execute
    any operational action.
    """
    if not incident_id and not shipment_id:
        raise ValueError("incident_id or shipment_id is required")
    with _operations_connection() as connection:
        if incident_id:
            rows = connection.execute(
                "SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM incidents WHERE shipment_id = ? ORDER BY created_at DESC",
                (shipment_id,),
            ).fetchall()
        return [dict(row) for row in rows]


@tool
def request_human_approval(
    incident_id: str, action: str, requested_by: str = "logistics-agent"
) -> dict[str, str]:
    """Create a pending approval for a controlled operational action.

    Use this before rerouting, cargo disposal, hold release, or customer
    contact. The tool creates a review request only. It never approves or
    executes the requested action.
    """
    if not incident_id.strip() or not action.strip():
        raise ValueError("incident_id and action are required")
    approval_id = f"APR-{uuid.uuid4().hex[:12].upper()}"
    timestamp = _now()
    with _operations_connection() as connection:
        connection.execute(
            "INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                approval_id,
                incident_id.strip(),
                action.strip(),
                "pending",
                requested_by.strip(),
                None,
                timestamp,
                timestamp,
            ),
        )
        connection.commit()
    record_metric("approval_requested", request_id=ACTIVE_REQUEST_ID.get())
    return {"approval_id": approval_id, "incident_id": incident_id, "status": "pending"}


@tool
def health_check_dependencies() -> dict[str, Any]:
    """Check configured SQL, Pinecone, and weather dependencies.

    Returns an ``ok`` or error status for each dependency without returning
    credentials, API keys, or database contents. Use this for startup and
    operational diagnostics, not as a substitute for a business decision.
    """
    result: dict[str, Any] = {}
    try:
        with _build_agent_database().connect() as connection:
            connection.execute(text("SELECT 1"))
        result["sql"] = "ok"
    except Exception as error:
        result["sql"] = f"error: {type(error).__name__}"
    try:
        from pinecone import Pinecone

        Pinecone(api_key=os.environ["PINECONE_API_KEY"]).Index(
            os.environ["PINECONE_INDEX_NAME"]
        ).describe_index_stats()
        result["pinecone"] = "ok"
    except Exception as error:
        result["pinecone"] = f"error: {type(error).__name__}"
    try:
        get_weather.invoke({"latitude": 33.77, "longitude": -118.19})
        result["weather"] = "ok"
    except Exception as error:
        result["weather"] = f"error: {type(error).__name__}"
    return result


def _contains_forbidden_key(value: Any) -> bool:
    """Reject secret-like keys anywhere in a nested audit payload."""
    forbidden = {"password", "api_key", "token", "secret"}
    if isinstance(value, dict):
        return any(
            key.lower() in forbidden or _contains_forbidden_key(nested)
            for key, nested in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item) for item in value)
    return False


@tool
def write_audit_event(
    event_type: str,
    payload: dict[str, Any],
    request_id: str | None = None,
    actor: str = "logistics-agent",
) -> dict[str, str]:
    """Write a sanitized development audit event without secrets.

    Audit payloads may include request IDs, shipment IDs, retrieved SOP
    sections, telemetry summaries, triggered rules, model output summaries,
    incident IDs, and approval IDs. Passwords, API keys, tokens, and secrets
    are rejected recursively. ``request_id`` correlates events from one
    request, and ``actor`` identifies the writer. This tool records an audit
    event only and has no operational side effects.
    """
    if not event_type.strip():
        raise ValueError("event_type must not be empty")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    effective_request_id = request_id or ACTIVE_REQUEST_ID.get()
    if effective_request_id is not None and not effective_request_id.strip():
        raise ValueError("request_id must not be blank")
    if not actor.strip():
        raise ValueError("actor must not be blank")
    if _contains_forbidden_key(payload):
        raise ValueError("audit payload contains a prohibited secret field")
    event_id = f"AUD-{uuid.uuid4().hex[:12].upper()}"
    with _operations_connection() as connection:
        connection.execute(
            """
            INSERT INTO audit_events
                (event_id, event_type, request_id, actor, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event_type.strip(),
                effective_request_id.strip() if effective_request_id else None,
                actor.strip(),
                json.dumps(payload),
                _now(),
            ),
        )
        connection.commit()
    return {
        "event_id": event_id,
        "event_type": event_type.strip(),
        "request_id": effective_request_id.strip() if effective_request_id else "",
    }


@tool
def get_audit_events(
    request_id: str | None = None,
    event_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Read sanitized audit events for investigation or request tracing."""
    if request_id is not None and not request_id.strip():
        raise ValueError("request_id must not be blank")
    if event_type is not None and not event_type.strip():
        raise ValueError("event_type must not be blank")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    query = """
        SELECT event_id, event_type, request_id, actor, payload_json, created_at
        FROM audit_events
        WHERE (? IS NULL OR request_id = ?)
          AND (? IS NULL OR event_type = ?)
        ORDER BY created_at DESC
        LIMIT ?
    """
    with _operations_connection() as connection:
        rows = connection.execute(
            query,
            (
                request_id.strip() if request_id else None,
                request_id.strip() if request_id else None,
                event_type.strip() if event_type else None,
                event_type.strip() if event_type else None,
                limit,
            ),
        ).fetchall()
    return [
        {
            **{key: row[key] for key in ("event_id", "event_type", "request_id", "actor", "created_at")},
            "payload": json.loads(row["payload_json"]),
        }
        for row in rows
    ]
