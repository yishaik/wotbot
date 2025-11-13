import json
import logging
from typing import Any, Dict, List, Optional

import requests

from ..config import settings

log = logging.getLogger(__name__)


class MCPHttpClient:
    """
    Thin MCP client over HTTP JSON-RPC. Servers should accept a POST with a JSON-RPC
    payload. This client supports two basic methods:
      - list_tools
      - call_tool
    The exact JSON-RPC method names can be customized by servers; by default we use
    'tools/list' and 'tools/call'.
    """

    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.headers = {"Content-Type": "application/json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def _rpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        try:
            resp = self.session.post(self.base_url, headers=self.headers, json=payload, timeout=settings.http_timeout_sec)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}
        if "error" in data:
            return {"ok": False, "error": data["error"]}
        return {"ok": True, "result": data.get("result")}

    def list_tools(self) -> Dict[str, Any]:
        return self._rpc("tools/list", {})

    def call_tool(self, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return self._rpc("tools/call", {"tool": tool, "arguments": arguments})


def mcp_list_all() -> Dict[str, Any]:
    servers = settings.mcp_servers
    if not servers:
        return {"ok": False, "error": "No MCP servers configured"}
    out: List[Dict[str, Any]] = []
    for idx, srv in enumerate(servers):
        client = MCPHttpClient(srv, settings.mcp_token)
        res = client.list_tools()
        out.append({"server": srv, "response": res})
    return {"ok": True, "servers": out}


def mcp_call(server: str, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    servers = list(settings.mcp_servers)
    if not servers:
        return {"ok": False, "error": "No MCP servers configured"}
    # Allow addressing by index or by exact base URL
    chosen: Optional[str] = None
    try:
        idx = int(server)
        if 0 <= idx < len(servers):
            chosen = servers[idx]
    except Exception:
        # not an int
        pass
    if chosen is None:
        for s in servers:
            if s.rstrip('/') == server.rstrip('/'):
                chosen = s
                break
    if chosen is None:
        return {"ok": False, "error": f"Unknown MCP server: {server}"}

    client = MCPHttpClient(chosen, settings.mcp_token)
    return client.call_tool(tool, arguments or {})

