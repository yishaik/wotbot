import json
import logging
import time
from typing import Any, Dict, Optional

from openai import OpenAI

from ..config import settings
from ..tools.schemas import tool_schemas
from .tool_router import ToolRouter


log = logging.getLogger(__name__)


class AssistantsBackend:
    def __init__(self):
        self.client = OpenAI()
        self._assistant_id: Optional[str] = settings.openai_assistant_id or None
        self.tools = ToolRouter()

    def _ensure_assistant(self) -> str:
        if self._assistant_id:
            return self._assistant_id
        # Create an assistant with current tool schemas
        asst = self.client.beta.assistants.create(
            model=settings.openai_model,
            name="WotBot",
            instructions=(
                "You are WotBot, a WhatsApp assistant. Keep replies concise and mobile-friendly. "
                "Use provided functions for code, HTTP, MCP, and system info."
            ),
            tools=[{"type": "function", "function": t["function"]} for t in tool_schemas()],
        )
        self._assistant_id = asst.id
        log.info("Created assistant %s", asst.id)
        return asst.id

    def _get_or_create_thread(self, user_id: str) -> str:
        # We can keep thread IDs ephemeral by creating each time; or persist per user in memory.
        # For persistence across restarts, store in session memory later if desired.
        # Here, we cache in-memory in a dict on the instance.
        if not hasattr(self, "_threads"):
            self._threads = {}
        if user_id in self._threads:
            return self._threads[user_id]
        th = self.client.beta.threads.create()
        self._threads[user_id] = th.id
        return th.id

    def complete(self, user_id: str, user_text: str, system_prompt: Optional[str] = None) -> str:
        asst_id = self._ensure_assistant()
        thread_id = self._get_or_create_thread(user_id)

        # Add user message to thread
        self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_text,
        )

        # Start run, optionally override instructions
        run = self.client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=asst_id,
            instructions=system_prompt or None,
        )

        # Poll run until completion, handling tool calls
        while True:
            run = self.client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            status = run.status
            if status == "requires_action":
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                outputs = []
                for call in tool_calls:
                    name = call.function.name
                    args = call.function.arguments
                    log.info("Assistants requested tool: %s", name)
                    result = self.tools.call(name, args)
                    outputs.append({"tool_call_id": call.id, "output": json.dumps(result)})
                self.client.beta.threads.runs.submit_tool_outputs(
                    thread_id=thread_id,
                    run_id=run.id,
                    tool_outputs=outputs,
                )
                continue
            if status in {"queued", "in_progress", "cancelling"}:
                time.sleep(0.5)
                continue
            if status == "completed":
                break
            # failed/cancelled/expired
            log.warning("Run ended with status: %s", status)
            break

        # Fetch the latest assistant message in this run
        msgs = self.client.beta.threads.messages.list(thread_id=thread_id, order="desc", limit=10)
        text_out = ""
        for m in msgs.data:
            if m.role == "assistant" and m.run_id == run.id:
                # Concatenate text segments
                segs = []
                for c in m.content:
                    try:
                        if c.type == "text":
                            segs.append(c.text.value)
                    except Exception:
                        pass
                text_out = "\n".join(segs).strip()
                if text_out:
                    break
        return text_out or "(no content)"

