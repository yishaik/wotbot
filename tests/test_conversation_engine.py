import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


code_runner_stub = types.ModuleType("wotbot.tools.code_runner")
code_runner_stub.run_code = lambda *_, **__: {"ok": True}
sys.modules.setdefault("wotbot.tools.code_runner", code_runner_stub)

assistants_stub = types.ModuleType("wotbot.conversation.assistants_backend")


class _DummyAssistantsBackend:
    def complete(self, *_args, **_kwargs):
        return ""


assistants_stub.AssistantsBackend = _DummyAssistantsBackend
sys.modules.setdefault("wotbot.conversation.assistants_backend", assistants_stub)


from wotbot.conversation.engine import ConversationEngine
from wotbot.conversation.session_store import SessionStore
from wotbot.config import settings


class ConversationEngineTest(unittest.TestCase):
    def setUp(self):
        self.store = SessionStore()
        self.orig_assistants = settings.openai_use_assistants
        self.orig_responses = settings.openai_use_responses
        settings.openai_use_assistants = False
        settings.openai_use_responses = False

    def tearDown(self):
        settings.openai_use_assistants = self.orig_assistants
        settings.openai_use_responses = self.orig_responses

    def test_converse_with_responses_and_tools(self):
        settings.openai_use_responses = True

        with patch("wotbot.conversation.engine.OpenAIClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.responses_with_tools.side_effect = [
                SimpleNamespace(
                    output=[
                        {
                            "role": "assistant",
                            "content": [],
                            "tool_calls": [
                                {
                                    "id": "tool-1",
                                    "type": "function",
                                    "function": {"name": "get_system_status", "arguments": "{}"},
                                }
                            ],
                        }
                    ],
                    output_text="",
                ),
                SimpleNamespace(
                    output=[
                        {
                            "role": "assistant",
                            "content": [{"type": "text", "text": "All done"}],
                            "tool_calls": [],
                        }
                    ],
                    output_text="All done",
                ),
            ]
            mock_client.chat_with_tools = MagicMock()

            engine = ConversationEngine(self.store)
            engine.tools.call = MagicMock(return_value={"ok": True, "status": "green"})

            result = engine.converse("user-1", "hello")

            self.assertEqual(result, ["All done"])
            self.assertEqual(self.store.get("user-1").messages[-1].content, "All done")
            mock_client.responses_with_tools.assert_called()
            mock_client.chat_with_tools.assert_not_called()
            engine.tools.call.assert_called_once_with("get_system_status", "{}")

    def test_converse_chat_fallback(self):
        settings.openai_use_responses = False

        with patch("wotbot.conversation.engine.OpenAIClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.responses_with_tools = MagicMock()
            mock_client.chat_with_tools.return_value = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Hi there", tool_calls=None))]
            )

            engine = ConversationEngine(self.store)

            result = engine.converse("user-2", "hi")

            self.assertEqual(result, ["Hi there"])
            mock_client.chat_with_tools.assert_called_once()
            mock_client.responses_with_tools.assert_not_called()


if __name__ == "__main__":
    unittest.main()
