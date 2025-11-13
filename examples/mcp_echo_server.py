#!/usr/bin/env python3
"""
Example MCP HTTP JSON-RPC server.

Endpoints:
  POST /jsonrpc with JSON-RPC 2.0 body.

Methods:
  tools/list -> returns a list of available tools
  tools/call -> executes a tool by name with arguments

Tools:
  echo: returns the arguments back (for testing)
  add: returns sum of two numbers {a, b}

Run:
  python examples/mcp_echo_server.py --host 127.0.0.1 --port 9010
Then configure MCP_SERVERS to http://127.0.0.1:9010/jsonrpc in Admin.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import argparse


TOOLS = {
    "echo": {
        "name": "echo",
        "description": "Returns provided arguments.",
        "schema": {"type": "object", "additionalProperties": True},
    },
    "add": {
        "name": "add",
        "description": "Add two numbers a and b.",
        "schema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    },
}


def rpc_list_tools():
    return [{"name": t["name"], "description": t["description"], "schema": t["schema"]} for t in TOOLS.values()]


def rpc_call_tool(tool: str, arguments: dict):
    if tool == "echo":
        return {"ok": True, "echo": arguments}
    if tool == "add":
        try:
            return {"ok": True, "sum": float(arguments.get("a", 0)) + float(arguments.get("b", 0))}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": f"Unknown tool: {tool}"}


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        if self.path != "/jsonrpc":
            self._send_json(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            method = payload.get("method")
            params = payload.get("params", {})
            rid = payload.get("id")
            if method == "tools/list":
                result = rpc_list_tools()
                self._send_json(200, {"jsonrpc": "2.0", "id": rid, "result": result})
                return
            if method == "tools/call":
                result = rpc_call_tool(params.get("tool"), params.get("arguments") or {})
                self._send_json(200, {"jsonrpc": "2.0", "id": rid, "result": result})
                return
            self._send_json(400, {"jsonrpc": "2.0", "id": rid, "error": f"Unknown method: {method}"})
        except Exception as e:
            self._send_json(500, {"jsonrpc": "2.0", "id": None, "error": str(e)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9010)
    args = ap.parse_args()
    httpd = HTTPServer((args.host, args.port), Handler)
    print(f"MCP example server on http://{args.host}:{args.port}/jsonrpc")
    httpd.serve_forever()


if __name__ == "__main__":
    main()

