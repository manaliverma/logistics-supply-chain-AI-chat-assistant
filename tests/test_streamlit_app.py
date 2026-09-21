import unittest
from unittest.mock import patch

from src import streamlit_app


class StreamlitAppTests(unittest.TestCase):
    def test_greetings_use_fast_path(self):
        self.assertTrue(streamlit_app._is_greeting(" hi! "))
        self.assertTrue(streamlit_app._is_greeting("Good morning"))
        self.assertFalse(streamlit_app._is_greeting("check shipment status"))

    def test_stream_turn_passes_request_id_to_graph_state(self):
        class FakeGraph:
            def stream(self, state, config, stream_mode):
                self.state = state
                self.config = config
                self.stream_mode = stream_mode
                return iter([])

        graph = FakeGraph()
        with patch.object(
            streamlit_app.st.session_state,
            "thread_id",
            "REQ-STREAMLIT-1",
            create=True,
        ):
            answer, traces = streamlit_app._run_turn("Check status.", graph)

        self.assertEqual(answer, "")
        self.assertEqual(traces, [])
        self.assertEqual(graph.state["request_id"], "REQ-STREAMLIT-1")
        self.assertEqual(graph.state["status"], "started")
        self.assertEqual(
            graph.config["configurable"]["thread_id"],
            "REQ-STREAMLIT-1",
        )
        self.assertEqual(graph.stream_mode, "updates")


if __name__ == "__main__":
    unittest.main()
