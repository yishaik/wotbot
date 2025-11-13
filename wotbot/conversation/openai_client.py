import logging
from typing import Any, Dict, List
from openai import OpenAI
from ..config import settings


log = logging.getLogger(__name__)


class OpenAIClient:
    def __init__(self):
        self.client = OpenAI()
        self.model = settings.openai_model

    def chat_with_tools(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]):
        """
        Uses Chat Completions with function/tool calling. Returns the raw response dict.
        """
        log.debug("Calling OpenAI Chat Completions with tools: %s", [t.get("function", {}).get("name") for t in tools])
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0.3,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        return resp

    def responses_with_tools(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]):
        """Call the Responses API while translating chat-style messages to the new schema."""

        formatted = [self._format_responses_message(m) for m in messages]
        log.debug(
            "Calling OpenAI Responses with tools: %s",
            [t.get("function", {}).get("name") for t in tools],
        )
        return self.client.responses.create(
            model=self.model,
            input=formatted,
            tools=tools,
        )

    @staticmethod
    def _format_responses_message(message: Dict[str, Any]) -> Dict[str, Any]:
        role = message.get("role", "user")
        content = message.get("content")

        if isinstance(content, list):
            formatted_content: List[Dict[str, str]] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") and "text" in part:
                    formatted_content.append(part)
                else:
                    formatted_content.append({"type": "text", "text": str(part)})
        elif content is None:
            formatted_content = []
        else:
            formatted_content = [{"type": "text", "text": str(content)}]

        formatted: Dict[str, Any] = {"role": role, "content": formatted_content}

        if "tool_calls" in message:
            formatted["tool_calls"] = message["tool_calls"]
        if "tool_call_id" in message:
            formatted["tool_call_id"] = message["tool_call_id"]

        return formatted

