"""LangGraph orchestration for the governed logistics assistant.

The graph delegates tool selection and multi-step reasoning to a ReAct
reasoner, while the tools remain the only path to operational evidence and
governance records.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AnyMessage, HumanMessage
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from src.agent_tools import (
    ACTIVE_REQUEST_ID,
    evaluate_shipment_routing,
    get_audit_events,
    get_incident_status,
    get_route,
    get_weather,
    health_check_dependencies,
    query_telemetry,
    record_incident,
    request_human_approval,
    search_sop_compliance,
    write_audit_event,
)
from src.observability import record_failure, record_metric

ROOT = Path(__file__).resolve().parents[1]
SYSTEM_PROMPT_PATH = ROOT / "src/prompts/system_prompt.txt"
load_dotenv()
CHECKPOINTER = InMemorySaver()


class LogisticsState(TypedDict, total=False):
    """State carried through one logistics assistant request.

    ``messages`` contains the user, model, and tool messages used by the
    reasoner. ``request_id`` correlates the graph run with audit records.
    ``shipment_id`` carries optional shipment context, and ``status`` tracks
    the graph lifecycle.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    request_id: str
    shipment_id: str | None
    status: str


def load_system_prompt() -> str:
    """Load the agent's governed instructions from the tracked prompt file."""
    if not SYSTEM_PROMPT_PATH.is_file():
        raise FileNotFoundError(f"System prompt not found: {SYSTEM_PROMPT_PATH}")
    prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(f"System prompt is empty: {SYSTEM_PROMPT_PATH}")
    return prompt


def _build_reasoner():
    provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("Missing GEMINI_API_KEY in .env")
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
            temperature=0,
            google_api_key=api_key,
        )
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY in .env")
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
            api_key=api_key,
        )
    raise ValueError("LLM_PROVIDER must be 'gemini' or 'openai'")


def _toolset():
    return [
        query_telemetry,
        search_sop_compliance,
        get_weather,
        get_route,
        evaluate_shipment_routing,
        record_incident,
        get_incident_status,
        get_audit_events,
        request_human_approval,
        health_check_dependencies,
        write_audit_event,
    ]


def _build_agent():
    """Create the checkpointed LangChain agent with the external prompt."""
    return create_agent(
        model=_build_reasoner(),
        tools=_toolset(),
        system_prompt=load_system_prompt(),
        name="logistics_reasoner",
        checkpointer=CHECKPOINTER,
    )


def _log_agent_event(event_type: str, payload: dict[str, Any]) -> dict[str, str]:
    """Record an orchestrator lifecycle event without exposing user content."""
    return write_audit_event.invoke(
        {
            "event_type": event_type,
            "payload": payload,
            "actor": "orchestrator",
        }
    )


def build_graph():
    """Compile the LangGraph workflow used for one assistant request.

    The compiled graph has one orchestration node:

    ``START -> reasoner -> END``

    The ``reasoner`` node wraps the LangChain agent. The agent may call the
    allowlisted logistics tools repeatedly before returning its final answer.
    Building the graph initializes the model and registers tools, but does not
    invoke the model or execute a tool.
    """
    agent = _build_agent()

    def reason(state: LogisticsState) -> dict[str, Any]:
        """Run the LLM agent for the current state and store its messages."""
        request_token = ACTIVE_REQUEST_ID.set(state["request_id"])
        started = datetime.now(timezone.utc)
        record_metric("request_count", request_id=state["request_id"])
        try:
            _log_agent_event(
                "agent_request_started",
                {
                    "shipment_id": state.get("shipment_id"),
                    "message_count": len(state.get("messages", [])),
                    "provider": os.getenv("LLM_PROVIDER", "gemini").strip().lower(),
                },
            )
            try:
                result = agent.invoke(
                    {"messages": state.get("messages", [])},
                    config={"configurable": {"thread_id": state["request_id"]}},
                )
            except Exception as error:
                record_failure(error, request_id=state["request_id"])
                _log_agent_event(
                    "agent_request_failed",
                    {"error_type": type(error).__name__},
                )
                raise
            _log_agent_event(
                "agent_request_completed",
                {
                    "message_count": len(result.get("messages", [])),
                    "status": "completed",
                },
            )
            record_metric("request_success", request_id=state["request_id"])
        finally:
            record_metric(
                "model_latency_ms",
                (datetime.now(timezone.utc) - started).total_seconds() * 1000,
                request_id=state["request_id"],
            )
            ACTIVE_REQUEST_ID.reset(request_token)
        return {"messages": result["messages"], "status": "completed"}

    graph = StateGraph(LogisticsState)
    graph.add_node("reasoner", reason)
    # The agent handles its internal tool loop; this outer graph owns request flow.
    graph.add_edge(START, "reasoner")
    graph.add_edge("reasoner", END)
    return graph.compile()


def stream_request(
    question: str,
    *,
    request_id: str,
):
    """Stream agent state updates for one checkpointed conversation turn.

    The yielded mapping contains agent node updates. Tool-call updates can be
    displayed separately by callers; the final assistant text is contained in
    the latest message update.
    """
    if not question.strip():
        raise ValueError("question must not be empty")
    if not request_id.strip():
        raise ValueError("request_id must not be empty")

    agent = _build_agent()
    request_token = ACTIVE_REQUEST_ID.set(request_id)
    completed = False
    try:
        _log_agent_event(
            "agent_request_started",
            {
                "message_count": 1,
                "provider": os.getenv("LLM_PROVIDER", "gemini").strip().lower(),
            },
        )
        yield from agent.stream(
            {"messages": [("user", question.strip())]},
            config={"configurable": {"thread_id": request_id}},
            stream_mode="updates",
        )
        completed = True
    finally:
        _log_agent_event(
            "agent_request_completed" if completed else "agent_request_failed",
            {
                "status": "completed" if completed else "failed",
                **(
                    {}
                    if completed
                    else {"error_type": "stream_interrupted_or_failed"}
                ),
            },
        )
        ACTIVE_REQUEST_ID.reset(request_token)


def run_request(
    question: str,
    *,
    shipment_id: str | None = None,
    request_id: str | None = None,
):
    """Execute one user question through the governed logistics graph.

    A request ID is generated when the caller does not provide one. The ID is
    used as the graph thread identifier so tool results and audit records can
    be correlated to the same request.
    """
    if not question.strip():
        raise ValueError("question must not be empty")
    request_id = request_id or f"REQ-{uuid.uuid4().hex[:12].upper()}"
    state: LogisticsState = {
        "messages": [HumanMessage(content=question.strip())],
        "request_id": request_id,
        "shipment_id": shipment_id,
        "status": "started",
    }
    return build_graph().invoke(
        state,
        config={"configurable": {"thread_id": request_id}},
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the logistics ReAct agent.")
    parser.add_argument("question", help="Question for the logistics assistant.")
    parser.add_argument("--shipment-id", help="Optional shipment identifier.")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Keep one checkpointed conversation open for multiple questions.",
    )
    args = parser.parse_args()
    if args.interactive:
        thread_id = f"REQ-{uuid.uuid4().hex[:12].upper()}"
        while True:
            try:
                user_input = input("\nDispatcher > ").strip()
            except EOFError:
                break
            if user_input.lower() in {"exit", "quit"}:
                break
            for event in stream_request(user_input, request_id=thread_id):
                for node_name, node_state in event.items():
                    messages = node_state.get("messages", [])
                    if not messages:
                        continue
                    latest_message = messages[-1]
                    if latest_message.content:
                        print(f"\n[{node_name}]\n{latest_message.content}")
        raise SystemExit(0)
    result = run_request(args.question, shipment_id=args.shipment_id)
    print(result["messages"][-1].content)