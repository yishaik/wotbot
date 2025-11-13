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

    def responses_complete_text(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> str:
        """
        Call the Responses API with tools and return the final output text.
        Handles requires_action by executing tool calls and submitting outputs.
        """
        if not hasattr(self.client, "responses"):
            raise RuntimeError("Responses API not available in this OpenAI SDK")

        formatted_input = _format_responses_input(messages)
        log.debug("Calling OpenAI Responses with tools: %s", [t.get("function", {}).get("name") for t in tools])
        resp = self.client.responses.create(model=self.model, input=formatted_input, tools=tools)

        # Tool-calling loop
        while getattr(resp, "status", None) == "requires_action":
            tool_calls = _get(resp, ["required_action", "submit_tool_outputs", "tool_calls"]) or []
            outputs = []
            for call in tool_calls:
                name = _get(call, ["function", "name"]) or ""
                args = _get(call, ["function", "arguments"]) or "{}"
                result = self._execute_tool(name, args)
                outputs.append({"tool_call_id": _get(call, ["id"]) or "", "output": _json_dumps(result)})
            resp = self.client.responses.submit_tool_outputs(response_id=_get(resp, ["id"]) or getattr(resp, "id"), tool_outputs=outputs)
            # retrieve until completed
            status = getattr(resp, "status", None)
            if status in {"queued", "in_progress", "requires_action"}:
                resp = self.client.responses.retrieve(_get(resp, ["id"]) or getattr(resp, "id"))

        text = _output_text(resp)
        return text or "(no content)"

    def _execute_tool(self, name: str, args_json: str) -> Dict[str, Any]:
        from .tool_router import ToolRouter
        router = ToolRouter()
        return router.call(name, args_json)


def _format_responses_input(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "tool":
            # Tool output is handled via submit_tool_outputs, not input stream
            continue
        if isinstance(content, list):
            text = "\n".join(str(p.get("text", "")) if isinstance(p, dict) else str(p) for p in content)
        else:
            text = str(content or "")
        ctype = "input_text" if role in {"user", "system"} else "output_text"
        out.append({
            "role": role if role in {"user", "assistant", "system"} else "user",
            "content": [{"type": ctype, "text": text}],
        })
    return out


def _get(obj: Any, path: List[str]) -> Any:
    cur = obj
    try:
        for k in path:
            if isinstance(cur, dict):
                cur = cur.get(k)
            else:
                cur = getattr(cur, k)
        return cur
    except Exception:
        return None


def _output_text(resp: Any) -> str:
    # Prefer direct attribute if present
    if hasattr(resp, "output_text") and getattr(resp, "output_text"):
        return getattr(resp, "output_text")
    # Otherwise, look in output list for output_text parts
    parts = _get(resp, ["output"]) or []
    texts: List[str] = []
    for p in parts or []:
        data = p if isinstance(p, dict) else {}
        typ = data.get("type")
        if typ == "output_text":
            val = data.get("text") or data.get("content") or ""
            if isinstance(val, str):
                texts.append(val)
            elif isinstance(val, list):
                texts.extend([str(v) for v in val if v])
    return "\n".join(t for t in texts if t)
