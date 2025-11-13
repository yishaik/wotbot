import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


from wotbot.conversation.openai_client import OpenAIClient


class OpenAIClientResponsesTest(unittest.TestCase):
    def test_responses_with_tools_formats_messages(self):
        dummy_create = MagicMock(return_value="ok")
        dummy_client = SimpleNamespace(responses=SimpleNamespace(create=dummy_create))

        with patch("wotbot.conversation.openai_client.OpenAI", return_value=dummy_client):
            client = OpenAIClient()

        messages = [
            {"role": "system", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "get_status", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "{\"ok\": true}"},
        ]

        result = client.responses_with_tools(messages, tools=[{"type": "function", "function": {"name": "get_status"}}])

        self.assertEqual(result, "ok")
        dummy_create.assert_called_once()
        kwargs = dummy_create.call_args.kwargs
        self.assertIn("input", kwargs)
        formatted = kwargs["input"]
        self.assertEqual(len(formatted), 3)
        self.assertEqual(formatted[0]["role"], "system")
        self.assertEqual(formatted[0]["content"], [{"type": "text", "text": "hi"}])
        self.assertEqual(formatted[1]["tool_calls"][0]["id"], "call-1")
        self.assertEqual(formatted[2]["tool_call_id"], "call-1")
        self.assertEqual(formatted[2]["content"][0]["text"], "{\"ok\": true}")


if __name__ == "__main__":
    unittest.main()
