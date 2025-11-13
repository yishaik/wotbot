import json
import logging
from typing import Any, Dict

from ..tools import code_runner, http_client, mcp_client, system_tools

log = logging.getLogger(__name__)


class ToolRouter:
    def __init__(self):
        pass

    def call(self, name: str, arguments_json: str) -> Dict[str, Any]:
        try:
            args = json.loads(arguments_json or "{}")
        except Exception as e:
            return {"ok": False, "error": f"Invalid JSON args: {e}"}

        try:
            if name == "run_code":
                return code_runner.run_code(args.get("language"), args.get("code", ""))
            if name == "http_request":
                return http_client.http_request(
                    method=args.get("method", "GET"),
                    url=args.get("url", ""),
                    headers=args.get("headers"),
                    params=args.get("params"),
                    body=args.get("body"),
                )
            if name == "mcp_call":
                return mcp_client.mcp_call(
                    server=args.get("server", "0"),
                    tool=args.get("tool", ""),
                    arguments=args.get("arguments") or {},
                )
            if name == "get_system_status":
                return system_tools.get_system_status()
            if name == "read_log":
                return system_tools.read_log(args.get("path", "app.log"), int(args.get("lines", 200)))
            if name == "read_config":
                return system_tools.read_config(args.get("path", ""))
            if name == "restart_self":
                return system_tools.restart_self()
        except Exception as e:
            log.exception("Tool '%s' raised error", name)
            return {"ok": False, "error": str(e)}

        return {"ok": False, "error": f"Unknown tool: {name}"}

