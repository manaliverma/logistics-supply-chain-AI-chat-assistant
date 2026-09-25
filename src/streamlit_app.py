"""Streamlit dispatch console for the governed logistics agent."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import streamlit as st
from langchain_core.messages import AIMessage, ToolMessage

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent_tools import get_audit_events, write_audit_event
from src.orchestrator import build_graph
from src.observability import evaluate_alerts, record_failure, record_metric


st.set_page_config(
    page_title="FDE Supply Chain Dispatch Console",
    page_icon="🧊",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource(show_spinner="Loading the logistics agent once for this process...")
def _cached_graph():
    """Build one reusable graph/model for all sessions in this Streamlit process."""
    return build_graph()


def _audit(event_type: str, payload: dict[str, Any], request_id: str) -> None:
    """Write UI lifecycle metadata without storing raw questions or responses."""
    try:
        write_audit_event.invoke(
            {
                "event_type": event_type,
                "payload": payload,
                "request_id": request_id,
                "actor": "streamlit-ui",
            }
        )
    except Exception as error:
        record_metric("audit_write_failure", request_id=request_id)
        st.warning(f"Audit logging unavailable: {type(error).__name__}")


def _load_graph(request_id: str):
    """Use the process cache, falling back to a normal graph build if needed."""
    try:
        started = time.perf_counter()
        graph = _cached_graph()
        record_metric("cache_initialization_ms", (time.perf_counter() - started) * 1000, request_id=request_id)
        _audit("streamlit_graph_cache_ready", {"cache": "hit_or_initialized"}, request_id)
        return graph, "cached"
    except Exception as cache_error:
        _audit(
            "streamlit_graph_cache_failed",
            {"error_type": type(cache_error).__name__},
            request_id,
        )
        try:
            graph = build_graph()
            _audit("streamlit_graph_fallback_ready", {"cache": "bypassed"}, request_id)
            return graph, "fallback"
        except Exception as load_error:
            record_failure(load_error, request_id=request_id)
            _audit(
                "streamlit_graph_load_failed",
                {"error_type": type(load_error).__name__},
                request_id,
            )
            raise


def _message_text(content: Any) -> str:
    """Convert provider text blocks into displayable text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("text")
        )
    return str(content) if content else ""


def _is_greeting(question: str) -> bool:
    """Return whether a message can be answered without loading the agent."""
    normalized = question.strip().lower().strip("!.,? ")
    return normalized in {
        "hi",
        "hello",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
    }


def _init_session() -> None:
    """Initialize browser-session state; Streamlit reruns preserve this state."""
    if "user_id" not in st.session_state:
        st.session_state.user_id = f"USR-{uuid.uuid4().hex[:12].upper()}"
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = f"REQ-{uuid.uuid4().hex[:12].upper()}"
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "graph_mode" not in st.session_state:
        st.session_state.graph_mode = "not loaded"


def _render_message(message: dict[str, Any]) -> None:
    """Render stored chat content and safe tool trace metadata."""
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        for trace in message.get("traces", []):
            with st.expander(
                f"{trace['kind']}: {trace['name']}",
                expanded=False,
            ):
                if "args" in trace:
                    st.json(trace["args"])
                else:
                    st.code(trace.get("content", ""), language="text")


def _run_turn(question: str, graph: Any) -> tuple[str, list[dict[str, Any]]]:
    """Stream one turn and return final text plus safe UI traces."""
    traces: list[dict[str, Any]] = []
    final_text = ""
    events = graph.stream(
        {
            "messages": [("user", question)],
            "request_id": st.session_state.thread_id,
            "status": "started",
        },
        config={"configurable": {"thread_id": st.session_state.thread_id}},
        stream_mode="updates",
    )
    for event in events:
        for node_name, node_state in event.items():
            for message in node_state.get("messages", []):
                if isinstance(message, AIMessage):
                    if message.tool_calls:
                        for tool_call in message.tool_calls:
                            traces.append(
                                {
                                    "kind": "tool input",
                                    "name": tool_call["name"],
                                    "args": tool_call.get("args", {}),
                                }
                            )
                            _audit(
                                "streamlit_tool_requested",
                                {
                                    "node": node_name,
                                    "tool": tool_call["name"],
                                },
                                st.session_state.thread_id,
                            )
                    text = _message_text(message.content)
                    if text:
                        final_text = text
                elif isinstance(message, ToolMessage):
                    traces.append(
                        {
                            "kind": "tool output",
                            "name": message.name or "tool",
                            "content": _message_text(message.content),
                        }
                    )
                    _audit(
                        "streamlit_tool_completed",
                        {
                            "node": node_name,
                            "tool": message.name or "tool",
                        },
                        st.session_state.thread_id,
                    )
    return final_text, traces


def _render_audit_view() -> None:
    """Display sanitized local audit events without invoking the model."""
    st.title("🛡️ Agent Audit Log")
    st.caption("Read-only view of the governed local audit store.")
    request_id = st.text_input(
        "Request ID",
        value=st.session_state.thread_id,
        help="Filter events to one browser conversation/thread.",
    )
    limit = st.slider("Events", min_value=1, max_value=100, value=30)
    if st.button("Refresh audit log"):
        st.rerun()
    events = get_audit_events.invoke({"request_id": request_id or None, "limit": limit})
    if not events:
        st.info("No audit events found.")
        return
    for event in reversed(events):
        st.code(
            f"{event['created_at']} | {event['event_type']} | "
            f"{event['event_id']} | request={event['request_id'] or '-'}\n"
            f"{json.dumps(event['payload'], sort_keys=True)}",
            language="text",
        )


def main() -> None:
    """Render the multi-user dispatch and audit application."""
    _init_session()
    with st.sidebar:
        st.title("Logistics and Supply Chain Agent")
        st.caption(f"User: {st.session_state.user_id}")
        st.caption(f"Thread: {st.session_state.thread_id}")
        graph_status = st.empty()
        graph_status.caption(f"Graph: {st.session_state.graph_mode}")
        page = st.radio("View", ["Dispatch Console", "Audit Log"])
        if st.button("New conversation", use_container_width=True):
            st.session_state.thread_id = f"REQ-{uuid.uuid4().hex[:12].upper()}"
            st.session_state.messages = []
            st.session_state.graph_mode = "not loaded"
            st.rerun()

    if page == "Audit Log":
        _render_audit_view()
        return

    st.title("🧊 Cold-Chain Incident Control Dashboard")
    for message in st.session_state.messages:
        _render_message(message)

    question = st.chat_input("Ask about telemetry, weather, routing, or compliance...")
    if not question:
        return

    st.session_state.messages.append({"role": "user", "content": question})
    record_metric("request_count", request_id=st.session_state.thread_id)
    request_started = time.perf_counter()
    _audit(
        "streamlit_user_message",
        {"message_length": len(question)},
        st.session_state.thread_id,
    )
    with st.chat_message("assistant"):
        try:
            if _is_greeting(question):
                answer = (
                    "Hello. I’m ready to check shipment telemetry, weather, "
                    "route risk, SOP compliance, incidents, and approvals."
                )
                elapsed_ms = round((time.perf_counter() - request_started) * 1000, 2)
                record_metric(
                    "request_latency_ms",
                    elapsed_ms,
                    request_id=st.session_state.thread_id,
                )
                st.markdown(answer)
                st.session_state.messages.append(
                    {"role": "assistant", "content": answer, "traces": []}
                )
                _audit(
                    "streamlit_fast_path_completed",
                    {"intent": "greeting", "duration_ms": elapsed_ms},
                    st.session_state.thread_id,
                )
                return

            st.session_state.graph_mode = "loading"
            graph_status.caption("Graph: loading")
            graph, mode = _load_graph(st.session_state.thread_id)
            st.session_state.graph_mode = mode
            graph_status.caption(f"Graph: {mode}")
            with st.status("Running governed agent workflow...", expanded=False):
                answer, traces = _run_turn(question, graph)
            if not answer:
                raise RuntimeError("The agent returned no final response")
            st.markdown(answer)
            st.session_state.messages.append(
                {"role": "assistant", "content": answer, "traces": traces}
            )
            _audit(
                "streamlit_response_rendered",
                {
                    "trace_count": len(traces),
                    "duration_ms": round(
                        (time.perf_counter() - request_started) * 1000, 2
                    ),
                },
                st.session_state.thread_id,
            )
            elapsed_ms = round((time.perf_counter() - request_started) * 1000, 2)
            record_metric("request_latency_ms", elapsed_ms, request_id=st.session_state.thread_id)
            record_metric("request_success", request_id=st.session_state.thread_id)
            evaluate_alerts(request_id=st.session_state.thread_id)
        except Exception as error:
            category = record_failure(error, request_id=st.session_state.thread_id)
            record_metric(
                "request_latency_ms",
                (time.perf_counter() - request_started) * 1000,
                request_id=st.session_state.thread_id,
            )
            _audit(
                "streamlit_request_failed",
                {
                    "error_type": type(error).__name__,
                    "duration_ms": round(
                        (time.perf_counter() - request_started) * 1000, 2
                    ),
                },
                st.session_state.thread_id,
            )
            record_metric("request_failure", request_id=st.session_state.thread_id)
            _audit(
                "streamlit_failure_classified",
                {"category": category},
                st.session_state.thread_id,
            )
            evaluate_alerts(request_id=st.session_state.thread_id)
            graph_status.caption(f"Graph: {st.session_state.graph_mode}")
            st.error(
                f"The request could not be completed ({type(error).__name__}). "
                "The session remains available; "
                "you can retry after checking the dependency or provider status."
            )


if __name__ == "__main__":
    main()
