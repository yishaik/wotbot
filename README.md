# WotBot — WhatsApp + OpenAI Tools Bot

An advanced WhatsApp bot built with FastAPI, Twilio, and OpenAI tool-calling. It supports sandboxed code execution, HTTP requests, MCP servers, and safe system management utilities.

## Features

- Twilio WhatsApp webhook with signature validation option.
- Conversation engine using OpenAI with tool-calling (Chat Completions by default).
- Tools:
  - Code execution (Python sandbox, optional JavaScript via Node).
  - HTTP/REST client with domain allowlist and redacted logging.
  - MCP thin client over HTTP JSON-RPC (list/call tools).
  - Safe system management: read logs/configs, basic system metrics, self-restart hook.
- Commands: `/help`, `/status`, `/restart_bot` (admin), `/tools`, `/mode dev|normal`, `/admin/status`, `/admin/restart`.
- Observability: rotating file logs, `/health` endpoint.

## Project Structure

```
app.py
wotbot/
  app.py
  config.py
  logging_config.py
  routes/
    health.py
    twilio_webhook.py
  conversation/
    engine.py
    openai_client.py
    session_store.py
    tool_router.py
  tools/
    _py_sandbox.py
    code_runner.py
    http_client.py
    mcp_client.py
    schemas.py
    system_tools.py
  utils/
    text_splitter.py
    twilio_utils.py
data/config/         # whitelisted config dir (create)
logs/                # log files (created at runtime)
requirements.txt
.env.example
Dockerfile
```

## Setup

1. Python 3.10+ recommended. Install dependencies:

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and fill values:

- `OPENAI_API_KEY`
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`
- `TWILIO_WHATSAPP_FROM` (e.g., `whatsapp:+14155238886` for sandbox)
- `PUBLIC_BASE_URL` (your publicly reachable URL used by Twilio for signature validation)
- Optional: `ADMIN_PHONE_NUMBERS` (comma-separated full WhatsApp numbers like `whatsapp:+1...`)
- Optional: Admin Web: `ADMIN_WEB_USERNAME`, `ADMIN_WEB_PASSWORD` to enable the admin UI at `/admin`.
- Optional: `OPENAI_USE_ASSISTANTS=true` to use the Assistants API.

3. Create directories:

```
mkdir -p logs data/config
```

## Run Locally

```
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Expose locally via `ngrok` or similar:

```
ngrok http 8000
```

Set `PUBLIC_BASE_URL` in `.env` to your ngrok URL.

## Twilio WhatsApp Setup

1. In the Twilio Console, enable the WhatsApp Sandbox or a WhatsApp-enabled number.
2. Set the inbound webhook (HTTP POST) to:

```
{PUBLIC_BASE_URL}/webhook/twilio/whatsapp
```

3. Send a WhatsApp message to your sandbox or number. You should get a reply from the bot.

The bot responds asynchronously: the webhook returns 200 OK immediately, and replies are sent via Twilio's REST API, avoiding webhook timeouts.

## Commands

- `/help` — Show commands.
- `/status` — Summarized system stats.
- `/tools` — List available tools.
- `/mode dev` or `/mode normal` — Toggle developer mode.
- `/restart_bot` — Admin-only safe restart.
- `/admin/status`, `/admin/restart` — Admin-only.

## OpenAI Integration

- Uses the official `openai` SDK.
- Defaults to Chat Completions with tool-calling (`gpt-4o-mini`).
- Tool schemas defined in `wotbot/tools/schemas.py`.
- Tool routing/exec handled by `wotbot/conversation/tool_router.py`.

Assistants API: enable by setting `OPENAI_USE_ASSISTANTS=true`. The bot creates an Assistant with function tools on first use (or uses `OPENAI_ASSISTANT_ID` if provided). Tool calls are handled via `runs.submit_tool_outputs`.

Chat Completions fallback: if `OPENAI_USE_ASSISTANTS=false`, the bot uses Chat Completions with function calling (the default).

## Tools

### Code Execution (Sandbox)

- Python snippets run in a subprocess with:
  - AST import ban, restricted builtins, resource limits, and timeout.
  - Intended only for short computations; no filesystem or network access.
- JavaScript snippets (optional) use Node's `vm` with a timeout. If Node is missing, the tool reports unsupported.

Environment controls:

- `CODE_EXEC_TIMEOUT_SEC` (default 5)
- `CODE_EXEC_MEMORY_MB` (default 128)

### HTTP/REST Tool

- `GET`, `POST`, `PUT`, `DELETE` with optional headers/params/body.
- All outgoing requests logged with sensitive headers redacted.
- Allowlist domains via `ALLOW_HTTP_DOMAINS` (comma-separated or `*`).

### MCP Tool

- Thin HTTP JSON-RPC client.
- Configure servers in `MCP_SERVERS` (comma-separated base URLs). Optional `MCP_TOKEN` is sent as `Authorization: Bearer`.
- Provides `mcp_call(server, tool, arguments)`.
- A helper `mcp_list_all()` is available for listing tools (can be hooked to a future command).

### System Tools (Safe)

- `get_system_status` — CPU, RAM, disk usage, uptime.
- `read_log(path, lines)` — Read from whitelisted `logs/`.
- `read_config(path)` — Read from whitelisted `data/config/`.
- `restart_self` — Triggers controlled exit so a supervisor (Docker/systemd) restarts the service.

Forbidden actions (by design): no arbitrary file deletion, no editing outside whitelisted dirs, no shell access, no network scanning.

## Health Check

- `GET /health` returns status, uptime, CPU, and memory usage.

## Deployment

### Docker

```
docker build -t wotbot:latest .
docker run --env-file .env -p 8000:8000 --name wotbot wotbot:latest
```

Run behind a reverse proxy (nginx/traefik) and set `PUBLIC_BASE_URL` accordingly.

### systemd (example unit)

```
[Unit]
Description=WotBot Service
After=network.target

[Service]
WorkingDirectory=/opt/wotbot
EnvironmentFile=/opt/wotbot/.env
ExecStart=/opt/wotbot/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Development Notes

- Logs are written to `logs/app.log` with rotation.
- Do not commit `.env` or secrets.
- To add a new tool: define schema in `tools/schemas.py`, implement logic in `tools/`, and add a branch in `conversation/tool_router.py`.

## Admin UI

- Enable by setting `ADMIN_WEB_USERNAME` and `ADMIN_WEB_PASSWORD`.
- Visit `/admin` and authenticate via HTTP Basic.
- You can update keys and settings at runtime; they persist to `data/config/settings.json`.
- Secrets are masked; leave blank to keep existing values.

## Security Considerations

- The Python code sandbox is constrained but not perfect; keep time/memory low and only allow small computations. Never grant file or network access.
- HTTP tool is controlled via allowlist and redaction; avoid sending secrets.
- Twilio signature validation can be enabled via `TWILIO_VALIDATE_SIGNATURE=true` (requires `PUBLIC_BASE_URL`).
