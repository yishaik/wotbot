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

