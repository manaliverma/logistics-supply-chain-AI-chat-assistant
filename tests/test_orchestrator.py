import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from src import orchestrator


class OrchestratorTests(unittest.TestCase):
    def test_system_prompt_contains_governed_flow_and_output_format(self):
        prompt = orchestrator.load_system_prompt()

        self.assertIn("query_telemetry", prompt)
        self.assertIn("search_sop_compliance", prompt)
        self.assertIn("evaluate_shipment_routing", prompt)
        self.assertIn("### 1. Executive Summary", prompt)
        self.assertIn("### 2. Telemetry & Environment Analysis", prompt)
        self.assertIn("### 3. Required Action Plan", prompt)

    def test_system_prompt_is_loaded_from_prompt_file(self):
        expected = Path(orchestrator.SYSTEM_PROMPT_PATH).read_text(
            encoding="utf-8"
        ).strip()

        self.assertEqual(orchestrator.load_system_prompt(), expected)

    def test_system_prompt_missing_file_fails_explicitly(self):
        with patch.object(
            orchestrator,
            "SYSTEM_PROMPT_PATH",
            Path("/tmp/logistics-missing-system-prompt.txt"),
        ):
            with self.assertRaises(FileNotFoundError):
                orchestrator.load_system_prompt()

    def test_system_prompt_empty_file_fails_explicitly(self):
        prompt_path = Path("/tmp/logistics-empty-system-prompt.txt")
        try:
            prompt_path.write_text("", encoding="utf-8")
            with patch.object(orchestrator, "SYSTEM_PROMPT_PATH", prompt_path):
                with self.assertRaises(ValueError):
                    orchestrator.load_system_prompt()
        finally:
            prompt_path.unlink(missing_ok=True)

    def test_toolset_contains_governed_tools(self):
        names = {tool.name for tool in orchestrator._toolset()}

        self.assertEqual(
            names,
            {
                "query_telemetry",
                "search_sop_compliance",
                "get_weather",
                "get_route",
                "evaluate_shipment_routing",
                "record_incident",
                "get_incident_status",
                "request_human_approval",
                "health_check_dependencies",
                "write_audit_event",
                "get_audit_events",
            },
        )

    def test_run_request_rejects_empty_question(self):
        with self.assertRaises(ValueError):
            orchestrator.run_request("   ")

    def test_stream_request_rejects_empty_question_or_thread(self):
        with self.assertRaises(ValueError):
            list(orchestrator.stream_request("   ", request_id="REQ-1"))
        with self.assertRaises(ValueError):
            list(orchestrator.stream_request("Check status", request_id=" "))

    def test_stream_request_uses_checkpointed_agent_updates(self):
        fake_agent = Mock()
        fake_agent.stream.return_value = iter(
            [{"model": {"messages": [AIMessage(content="Streamed result.")]}}]
        )

        with patch.object(orchestrator, "_build_agent", return_value=fake_agent):
            events = list(
                orchestrator.stream_request(
                    "Check shipment compliance.",
                    request_id="REQ-STREAM-1",
                )
            )

        self.assertEqual(events[0]["model"]["messages"][-1].content, "Streamed result.")
        fake_agent.stream.assert_called_once_with(
            {"messages": [("user", "Check shipment compliance.")]},
            config={"configurable": {"thread_id": "REQ-STREAM-1"}},
            stream_mode="updates",
        )

    def test_build_reasoner_uses_gemini_by_default(self):
        fake_model = Mock()
        with (
            patch.dict(
                orchestrator.os.environ,
                {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key"},
                clear=False,
            ),
            patch(
                "langchain_google_genai.ChatGoogleGenerativeAI",
                return_value=fake_model,
            ) as gemini,
        ):
            result = orchestrator._build_reasoner()

        self.assertIs(result, fake_model)
        gemini.assert_called_once()
        self.assertEqual(gemini.call_args.kwargs["temperature"], 0)
        self.assertEqual(
            gemini.call_args.kwargs["google_api_key"],
            "test-key",
        )

    def test_build_reasoner_rejects_unknown_provider(self):
        with patch.dict(
            orchestrator.os.environ,
            {"LLM_PROVIDER": "unknown"},
            clear=False,
        ):
            with self.assertRaises(ValueError):
                orchestrator._build_reasoner()

    def test_run_request_initializes_request_state(self):
        graph = Mock()
        graph.invoke.return_value = {"status": "completed"}

        with patch.object(orchestrator, "build_graph", return_value=graph):
            result = orchestrator.run_request(
                "Check shipment compliance.",
                shipment_id="US-FC-1",
                request_id="REQ-TEST-1",
            )

        self.assertEqual(result["status"], "completed")
        state = graph.invoke.call_args.args[0]
        config = graph.invoke.call_args.kwargs["config"]
        self.assertEqual(state["request_id"], "REQ-TEST-1")
        self.assertEqual(state["shipment_id"], "US-FC-1")
        self.assertEqual(state["status"], "started")
        self.assertIsInstance(state["messages"][0], HumanMessage)
        self.assertEqual(state["messages"][0].content, "Check shipment compliance.")
        self.assertEqual(
            config["configurable"]["thread_id"],
            "REQ-TEST-1",
        )

    def test_build_graph_passes_tools_to_react_reasoner(self):
        fake_reasoner = Mock()
        fake_react_agent = Mock()
        fake_react_agent.invoke.return_value = {
            "messages": [AIMessage(content="Decision complete.")]
        }

        with (
            patch.object(orchestrator, "_build_reasoner", return_value=fake_reasoner),
            patch.object(
                orchestrator,
                "create_agent",
                return_value=fake_react_agent,
            ) as create_agent,
        ):
            graph = orchestrator.build_graph()
            result = graph.invoke(
                {
                    "messages": [HumanMessage(content="Check shipment compliance.")],
                    "request_id": "REQ-TEST-2",
                    "status": "started",
                }
            )

        create_agent.assert_called_once()
        call = create_agent.call_args
        self.assertIs(call.kwargs["model"], fake_reasoner)
        self.assertEqual(call.kwargs["name"], "logistics_reasoner")
        self.assertEqual(
            call.kwargs["system_prompt"],
            orchestrator.load_system_prompt(),
        )
        self.assertIs(call.kwargs["checkpointer"], orchestrator.CHECKPOINTER)
        self.assertEqual(len(call.kwargs["tools"]), 11)
        fake_react_agent.invoke.assert_called_once()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["messages"][-1].content, "Decision complete.")

    def test_graph_logs_request_lifecycle(self):
        fake_reasoner = Mock()
        fake_agent = Mock()
        fake_agent.invoke.return_value = {
            "messages": [AIMessage(content="Decision complete.")]
        }
        with (
            patch.object(orchestrator, "_build_reasoner", return_value=fake_reasoner),
            patch.object(orchestrator, "create_agent", return_value=fake_agent),
            patch.object(orchestrator, "_log_agent_event") as log_event,
        ):
            orchestrator.build_graph().invoke(
                {
                    "messages": [HumanMessage(content="Check shipment.")],
                    "request_id": "REQ-LIFECYCLE",
                    "status": "started",
                }
            )

        self.assertEqual(
            [call.args[0] for call in log_event.call_args_list],
            ["agent_request_started", "agent_request_completed"],
        )


if __name__ == "__main__":
    unittest.main()
