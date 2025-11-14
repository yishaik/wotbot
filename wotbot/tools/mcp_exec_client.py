import json
import subprocess
import sys
from typing import Any, Dict, List, Optional


class MCPExecClient:
    """
    Minimal JSON-RPC client over stdio to a local MCP process.
    This assumes the process reads a single JSON-RPC request on stdin and writes
    a single JSON-RPC response on stdout, line-delimited. This is a pragmatic
    fallback and may need adapting for specific servers.
    """

    def __init__(self, command: List[str], cwd: Optional[str] = None, timeout: int = 10):
        self.command = command
        self.cwd = cwd
        self.timeout = timeout

    def _rpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        try:
            proc = subprocess.Popen(
                self.command,
                cwd=self.cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as e:
            return {"ok": False, "error": f"Command not found: {self.command[0]}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

        try:
            assert proc.stdin and proc.stdout
            proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()
            proc.stdin.close()
            out, err = proc.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            return {"ok": False, "error": "Timeout waiting for local MCP process"}
        except Exception as e:
            proc.kill()
            return {"ok": False, "error": str(e)}

        out = out.strip()
        if not out:
            return {"ok": False, "error": (err.strip() if err else "No output from process")}
        try:
            data = json.loads(out.splitlines()[-1])
        except json.JSONDecodeError:
            return {"ok": False, "error": "Invalid JSON from process", "raw": out[-2000:]}
        if "error" in data:
            return {"ok": False, "error": data["error"]}
        return {"ok": True, "result": data.get("result")}

    def list_tools(self) -> Dict[str, Any]:
        return self._rpc("tools/list", {})

    def call_tool(self, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return self._rpc("tools/call", {"tool": tool, "arguments": arguments})

