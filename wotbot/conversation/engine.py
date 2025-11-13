import logging
from typing import List, Dict, Any

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
        system_prompt = settings.assistant_instructions or (
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
            for _ in range(max_tool_iters):
                resp = self.openai.chat_with_tools(messages + tool_messages, tools)
                choice = resp.choices[0].message

                if getattr(choice, "tool_calls", None):
                    # Include the assistant message with tool calls
                    tool_messages.append({
                        "role": "assistant",
                        "content": choice.content or "",
                        "tool_calls": [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {"name": call.function.name, "arguments": call.function.arguments},
                            }
                            for call in choice.tool_calls
                        ],
                    })
                    for call in choice.tool_calls:
                        name = call.function.name
                        args = call.function.arguments
                        log.info("Model requested tool: %s", name)
                        result = self.tools.call(name, args)
                        # Append tool result message
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": json_dumps_safe(result)[:4000],
                        })
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
