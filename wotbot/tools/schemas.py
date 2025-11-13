from typing import List, Dict, Any


def tool_schemas() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "run_code",
                "description": "Run short code snippets in a sandbox (python or javascript).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "language": {
                            "type": "string",
                            "enum": ["python", "javascript"],
                            "description": "Language of the code snippet.",
                        },
                        "code": {"type": "string", "description": "Code to execute."},
                    },
                    "required": ["language", "code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "http_request",
                "description": "Perform an HTTP request (GET, POST, PUT, DELETE) with optional headers and query.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
                        "url": {"type": "string"},
                        "headers": {"type": "object", "additionalProperties": {"type": "string"}},
                        "params": {"type": "object", "additionalProperties": {"type": "string"}},
                        "body": {"type": ["object", "string", "null"]},
                    },
                    "required": ["method", "url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "mcp_call",
                "description": "Call a tool on a configured MCP server.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "server": {"type": "string", "description": "MCP server base URL key or index."},
                        "tool": {"type": "string", "description": "Tool name to invoke."},
                        "arguments": {"type": "object", "additionalProperties": True},
                    },
                    "required": ["server", "tool"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_system_status",
                "description": "Report system info: CPU, RAM, disk, uptime.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_log",
                "description": "Read recent application logs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path under logs directory."},
                        "lines": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 200},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_config",
                "description": "Read a configuration file from the whitelisted config directory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path under config directory."},
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "restart_self",
                "description": "Request the bot to restart itself in a controlled way.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]

