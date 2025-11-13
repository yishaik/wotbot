import json
import logging
from typing import List, Dict, Any, Iterable

from ..config import settings
from ..utils.text_splitter import split_for_whatsapp
from .session_store import SessionStore
from .openai_client import OpenAIClient
from .tool_router import ToolRouter
from ..tools.schemas import tool_schemas
from ..tools import system_tools
from .assistants_backend import AssistantsBackend


log = logging.getLogger(__name__)


class ConversationEngine:
    def __init__(self, sessions: SessionStore):
        self.sessions = sessions
        self.openai = OpenAIClient()
        self.tools = ToolRouter()
        self.assistants = AssistantsBackend()

    def handle_command(self, user_id: str, text: str) -> List[str]:
        cmd, *rest = text.strip().split(maxsplit=1)
        arg = rest[0] if rest else ""
        lower = cmd.lower()

        if lower in {"/help", "help"}:
            return [
                "Commands:\n/help\n/status\n/restart_bot (admin)\n/tools\n/mode dev|normal",
            ]
        if lower == "/status":
            s = system_tools.get_system_status()
            return [f"Status: CPU {s.get('cpu_percent')}%, RAM {s.get('memory',{}).get('percent')}%, Disk {s.get('disk',{}).get('percent')}%"]
        if lower == "/tools":
            names = [t["function"]["name"] for t in tool_schemas()]
            return ["Tools available: " + ", ".join(names)]
        if lower == "/mode":
            val = arg.strip().lower()
            if val in {"dev", "developer"}:
                self.sessions.set_developer_mode(user_id, True)
                return ["Developer mode ON"]
            elif val in {"normal", "default"}:
                self.sessions.set_developer_mode(user_id, False)
                return ["Developer mode OFF"]
            else:
                return ["Usage: /mode dev|normal"]
        if lower == "/restart_bot":
            if user_id not in settings.admin_phone_numbers:
                return ["Not authorized."]
            res = system_tools.restart_self()
            return [res.get("message", "Restart requested")] if res.get("ok") else ["Failed to restart"]
        if lower == "/admin/status":
            if user_id not in settings.admin_phone_numbers:
                return ["Not authorized."]
            s = system_tools.get_system_status()
            return [f"Admin status: CPU {s.get('cpu_percent')}%, RAM {s.get('memory',{}).get('percent')}%, Disk {s.get('disk',{}).get('percent')}%"]
        if lower == "/admin/restart":
            if user_id not in settings.admin_phone_numbers:
                return ["Not authorized."]
            res = system_tools.restart_self()
            return [res.get("message", "Restart requested")] if res.get("ok") else ["Failed to restart"]
        return ["Unknown command. Try /help"]

    def converse(self, user_id: str, text: str) -> List[str]:
        dev_default = settings.developer_mode_default
        if dev_default and not self.sessions.get(user_id).developer_mode:
            self.sessions.set_developer_mode(user_id, True)

        if text.strip().startswith("/"):
            return self.handle_command(user_id, text)

        # Build system prompt
        system_prompt = (
            "You are WotBot, a WhatsApp assistant. Keep replies concise, mobile-friendly. "
            "Use tools when helpful. Prefer bullets and short paragraphs. If output is long, suggest summarizing."
        )
        if self.sessions.get_developer_mode(user_id):
            system_prompt += " Developer mode is ON: you may provide more technical details."

        # Assemble messages
        history = self.sessions.get(user_id).messages
        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        for m in history[-10:]:  # trim to last 10 exchanges to keep light
            messages.append({"role": m.role, "content": m.content})
        messages.append({"role": "user", "content": text})

        # Store user message
        self.sessions.append(user_id, "user", text)

        # Choose backend
        if settings.openai_use_assistants:
            content = self.assistants.complete(user_id, text, system_prompt)
            content = content or "(no content)"
            self.sessions.append(user_id, "assistant", content)
            return split_for_whatsapp(content)
        else:
            tools = tool_schemas()

            max_tool_iters = 4
            tool_messages: List[Dict[str, Any]] = []

            if settings.openai_use_responses:
                for _ in range(max_tool_iters):
                    resp = self.openai.responses_with_tools(messages + tool_messages, tools)
                    assistant = _last_assistant_output(resp)
                    if not assistant:
                        break

                    tool_calls = _normalize_tool_calls(assistant.get("tool_calls"))
                    if tool_calls:
                        assistant_message: Dict[str, Any] = {
                            "role": "assistant",
                            "content": _content_to_text(assistant.get("content")),
                        }
                        if tool_calls:
                            assistant_message["tool_calls"] = tool_calls
                        tool_messages.append(assistant_message)
                        for call in tool_calls:
                            name = call.get("function", {}).get("name", "")
                            args = call.get("function", {}).get("arguments", "{}")
                            if not isinstance(args, str):
                                try:
                                    args = json.dumps(args)
                                except Exception:
                                    args = str(args)
                            log.info("Model requested tool: %s", name)
                            result = self.tools.call(name, args)
                            tool_messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": call.get("id"),
                                    "content": json_dumps_safe(result)[:4000],
                                }
                            )
                        continue

                    content = _content_to_text(assistant.get("content")) or _output_text(resp) or "(no content)"
                    self.sessions.append(user_id, "assistant", content)
                    return split_for_whatsapp(content)
            else:
                for _ in range(max_tool_iters):
                    resp = self.openai.chat_with_tools(messages + tool_messages, tools)
                    choice = resp.choices[0].message

                    if getattr(choice, "tool_calls", None):
                        # Include the assistant message with tool calls
                        tool_messages.append(
                            {
                                "role": "assistant",
                                "content": choice.content or "",
                                "tool_calls": [
                                    {
                                        "id": call.id,
                                        "type": "function",
                                        "function": {
                                            "name": call.function.name,
                                            "arguments": call.function.arguments,
                                        },
                                    }
                                    for call in choice.tool_calls
                                ],
                            }
                        )
                        for call in choice.tool_calls:
                            name = call.function.name
                            args = call.function.arguments
                            log.info("Model requested tool: %s", name)
                            result = self.tools.call(name, args)
                            # Append tool result message
                            tool_messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": call.id,
                                    "content": json_dumps_safe(result)[:4000],
                                }
                            )
                        # continue loop with appended tool_messages
                        continue
                    else:
                        content = choice.content or "(no content)"
                        self.sessions.append(user_id, "assistant", content)
                        return split_for_whatsapp(content)

            # If loop ends without content
            fallback = "I executed tools but didn't get a final message. Please try again."
            self.sessions.append(user_id, "assistant", fallback)
            return [fallback]


def json_dumps_safe(obj: Any) -> str:
    try:
        import json

        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)


def _last_assistant_output(response: Any) -> Dict[str, Any]:
    output = getattr(response, "output", None)
    if not output:
        return {}
    for item in reversed(list(_ensure_iterable(output))):
        data = _to_plain_dict(item)
        if data.get("role") == "assistant":
            return data
    return {}


def _output_text(response: Any) -> str:
    if hasattr(response, "output_text") and getattr(response, "output_text"):
        return getattr(response, "output_text")
    data = _to_plain_dict(response)
    return data.get("output_text", "")


def _content_to_text(content: Any) -> str:
    if not content:
        return ""
    if isinstance(content, str):
        return content
    parts = []
    for part in _ensure_iterable(content):
        if isinstance(part, str):
            if part:
                parts.append(part)
            continue
        data = _to_plain_dict(part)
        text = data.get("text")
        if not text and data.get("type") in {"output_text", "text"}:
            text = data.get("text")
        if not text and data.get("type") == "tool_call":
            continue
        if text:
            parts.append(text)
    return "\n".join(p for p in parts if p)


def _normalize_tool_calls(tool_calls: Any) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    if not tool_calls:
        return result
    for call in _ensure_iterable(tool_calls):
        data = _to_plain_dict(call)
        if data:
            if "function" in data and not isinstance(data["function"], dict):
                data["function"] = _to_plain_dict(data["function"])
            result.append(data)
    return result


def _ensure_iterable(value: Any) -> Iterable:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return value
    return [value]


def _to_plain_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        return {k: getattr(value, k) for k in vars(value) if not k.startswith("_")}
    return {}
