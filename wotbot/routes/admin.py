import base64
import logging
from typing import Dict

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status, Body, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..config import settings, apply_overrides, save_overrides
from ..tools import system_tools
from ..tools import mcp_client
from ..tools.mcp_exec_client import MCPExecClient
from ..tools.schemas import tool_schemas, all_tool_schemas
from openai import OpenAI
from urllib.parse import urlparse

log = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBasic()

env = Environment(
    loader=FileSystemLoader("wotbot/web/templates"),
    autoescape=select_autoescape(["html", "xml"]),
)


def require_auth(credentials: HTTPBasicCredentials = Depends(security)):
    if not settings.admin_web_username or not settings.admin_web_password:
        raise HTTPException(status_code=503, detail="Admin web not configured. Set ADMIN_WEB_USERNAME and ADMIN_WEB_PASSWORD.")
    correct_username = credentials.username == settings.admin_web_username
    correct_password = credentials.password == settings.admin_web_password
    if not (correct_username and correct_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate": "Basic"})
    return True


def _mask(value: str) -> str:
    if not value:
        return ""
    return "••••••" if len(value) > 0 else ""


@router.get("", response_class=HTMLResponse)
def admin_index(request: Request, _: bool = Depends(require_auth)):
    tpl = env.get_template("admin.html")
    ctx = {
        "OPENAI_API_KEY": _mask(settings.openai_api_key),
        "OPENAI_MODEL": settings.openai_model,
        "OPENAI_USE_RESPONSES": settings.openai_use_responses,
        "OPENAI_USE_ASSISTANTS": settings.openai_use_assistants,
        "OPENAI_ASSISTANT_ID": settings.openai_assistant_id or "",
        "ASSISTANT_INSTRUCTIONS": getattr(settings, 'assistant_instructions', '') or '',
        "OPENAI_TEMPERATURE": getattr(settings, 'openai_temperature', 0.3),
        "OPENAI_MAX_TOKENS": getattr(settings, 'openai_max_tokens', 600),
        "TWILIO_ACCOUNT_SID": _mask(settings.twilio_account_sid),
        "TWILIO_AUTH_TOKEN": _mask(settings.twilio_auth_token),
        "TWILIO_WHATSAPP_FROM": settings.twilio_whatsapp_from,
        "TWILIO_VALIDATE_SIGNATURE": settings.twilio_validate_signature,
        "PUBLIC_BASE_URL": settings.public_base_url,
        "ALLOW_HTTP_DOMAINS": ",".join(settings.allow_http_domains) if settings.allow_http_domains else "",
        "ADMIN_PHONE_NUMBERS": ",".join(settings.admin_phone_numbers) if settings.admin_phone_numbers else "",
        # MCP
        "MCP_SERVERS": ",".join(settings.mcp_servers) if settings.mcp_servers else "",
        "MCP_TOKEN": _mask(settings.mcp_token or ""),
        "message": request.query_params.get("msg", ""),
    }
    return tpl.render(**ctx)


@router.post("", response_class=HTMLResponse)
def admin_update(
    request: Request,
    _: bool = Depends(require_auth),
    OPENAI_API_KEY: str = Form(default=""),
    OPENAI_MODEL: str = Form(default=""),
    OPENAI_USE_ASSISTANTS: str = Form(default="off"),
    OPENAI_USE_RESPONSES: str = Form(default="off"),
    OPENAI_ASSISTANT_ID: str = Form(default=""),
    ASSISTANT_INSTRUCTIONS: str = Form(default=""),
    OPENAI_TEMPERATURE: str = Form(default=""),
    OPENAI_MAX_TOKENS: str = Form(default=""),
    TWILIO_ACCOUNT_SID: str = Form(default=""),
    TWILIO_AUTH_TOKEN: str = Form(default=""),
    TWILIO_WHATSAPP_FROM: str = Form(default=""),
    TWILIO_VALIDATE_SIGNATURE: str = Form(default="off"),
    PUBLIC_BASE_URL: str = Form(default=""),
    ALLOW_HTTP_DOMAINS: str = Form(default=""),
    ADMIN_PHONE_NUMBERS: str = Form(default=""),
    MCP_SERVERS: str = Form(default=""),
    MCP_TOKEN: str = Form(default=""),
):
    # Build overrides; for secrets, keep old if masked/empty
    overrides: Dict[str, str] = {}
    if OPENAI_API_KEY and not OPENAI_API_KEY.startswith("••••"):
        overrides["OPENAI_API_KEY"] = OPENAI_API_KEY.strip()
    if OPENAI_MODEL:
        overrides["OPENAI_MODEL"] = OPENAI_MODEL.strip()
    overrides["OPENAI_USE_ASSISTANTS"] = "true" if OPENAI_USE_ASSISTANTS == "on" else "false"
    overrides["OPENAI_USE_RESPONSES"] = "true" if OPENAI_USE_RESPONSES == "on" else "false"
    overrides["OPENAI_ASSISTANT_ID"] = OPENAI_ASSISTANT_ID.strip()
    if ASSISTANT_INSTRUCTIONS:
        overrides["ASSISTANT_INSTRUCTIONS"] = ASSISTANT_INSTRUCTIONS
    if OPENAI_TEMPERATURE:
        overrides["OPENAI_TEMPERATURE"] = OPENAI_TEMPERATURE
    if OPENAI_MAX_TOKENS:
        overrides["OPENAI_MAX_TOKENS"] = OPENAI_MAX_TOKENS

    if TWILIO_ACCOUNT_SID and not TWILIO_ACCOUNT_SID.startswith("••••"):
        overrides["TWILIO_ACCOUNT_SID"] = TWILIO_ACCOUNT_SID.strip()
    if TWILIO_AUTH_TOKEN and not TWILIO_AUTH_TOKEN.startswith("••••"):
        overrides["TWILIO_AUTH_TOKEN"] = TWILIO_AUTH_TOKEN.strip()
    if TWILIO_WHATSAPP_FROM:
        overrides["TWILIO_WHATSAPP_FROM"] = TWILIO_WHATSAPP_FROM.strip()
    overrides["TWILIO_VALIDATE_SIGNATURE"] = "true" if TWILIO_VALIDATE_SIGNATURE == "on" else "false"
    if PUBLIC_BASE_URL:
        overrides["PUBLIC_BASE_URL"] = PUBLIC_BASE_URL.strip()

    overrides["ALLOW_HTTP_DOMAINS"] = ALLOW_HTTP_DOMAINS.strip()
    overrides["ADMIN_PHONE_NUMBERS"] = ADMIN_PHONE_NUMBERS.strip()
    overrides["MCP_SERVERS"] = MCP_SERVERS.strip()
    if MCP_TOKEN and not MCP_TOKEN.startswith("••••"):
        overrides["MCP_TOKEN"] = MCP_TOKEN.strip()

    apply_overrides(overrides)
    save_overrides(overrides)

    # Redirect back to GET to avoid form resubmission
    return RedirectResponse(url=str(request.url), status_code=303)


@router.post("/restart")
def admin_restart(_: bool = Depends(require_auth)):
    res = system_tools.restart_self()
    return res


@router.post("/assistant/sync")
def assistant_sync(request: Request, _: bool = Depends(require_auth)):
    client = OpenAI()
    tools_payload = [{"type": "function", "function": t["function"]} for t in tool_schemas()]
    instructions = (
        "You are WotBot, a WhatsApp assistant. Keep replies concise and mobile-friendly. "
        "Use provided functions for code, HTTP, MCP, and system info."
    )
    asst_id = settings.openai_assistant_id
    try:
        if asst_id:
            client.beta.assistants.update(assistant_id=asst_id, model=settings.openai_model, tools=tools_payload, instructions=instructions)
            msg = f"Assistant {asst_id} updated with current tools."
        else:
            asst = client.beta.assistants.create(model=settings.openai_model, name="WotBot", instructions=instructions, tools=tools_payload)
            overrides = {"OPENAI_ASSISTANT_ID": asst.id}
            apply_overrides(overrides)
            save_overrides(overrides)
            msg = f"Assistant created: {asst.id}"
    except Exception as e:
        msg = f"Assistant sync failed: {e}"
    return RedirectResponse(url=f"/admin?msg={msg}", status_code=303)


@router.get("/api/assistant/info")
def assistant_info(_: bool = Depends(require_auth)):
    client = OpenAI()
    info = {
        "use_assistants": settings.openai_use_assistants,
        "assistant_id": settings.openai_assistant_id,
        "model": settings.openai_model,
    }
    if settings.openai_assistant_id:
        try:
            a = client.beta.assistants.retrieve(settings.openai_assistant_id)
            info["assistant"] = {
                "id": a.id,
                "name": getattr(a, "name", ""),
                "tools_count": len(getattr(a, "tools", []) or []),
            }
        except Exception as e:
            info["error"] = str(e)
    return JSONResponse(info)


@router.post("/api/assistant/sync")
def assistant_sync_api(_: bool = Depends(require_auth)):
    client = OpenAI()
    tools_payload = [{"type": "function", "function": t["function"]} for t in tool_schemas()]
    instructions = (
        "You are WotBot, a WhatsApp assistant. Keep replies concise and mobile-friendly. "
        "Use provided functions for code, HTTP, MCP, and system info."
    )
    asst_id = settings.openai_assistant_id
    try:
        if asst_id:
            client.beta.assistants.update(assistant_id=asst_id, model=settings.openai_model, tools=tools_payload, instructions=instructions)
            return {"ok": True, "message": f"Assistant {asst_id} updated"}
        else:
            asst = client.beta.assistants.create(model=settings.openai_model, name="WotBot", instructions=instructions, tools=tools_payload)
            overrides = {"OPENAI_ASSISTANT_ID": asst.id}
            apply_overrides(overrides)
            save_overrides(overrides)
            return {"ok": True, "message": f"Assistant created: {asst.id}", "assistant_id": asst.id}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/api/openai/models")
def api_openai_models(_: bool = Depends(require_auth)):
    client = OpenAI()
    try:
        models = client.models.list()
        ids = [m.id for m in getattr(models, 'data', [])]
        return {"ok": True, "models": ids}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/ai/ask")
def api_ai_ask(_: bool = Depends(require_auth), payload: Dict = Body(...)):
    from openai import OpenAI
    from ..tools.schemas import tool_schemas
    import psutil, platform
    q = (payload or {}).get("question", "Explain this admin page")
    include_logs = bool((payload or {}).get("include_logs"))
    include_health = bool((payload or {}).get("include_health"))
    include_tools = bool((payload or {}).get("include_tools"))

    # Sanitize config
    cfg = {
        "model": settings.openai_model,
        "use_assistants": settings.openai_use_assistants,
        "use_responses": settings.openai_use_responses,
        "public_base_url": settings.public_base_url,
        "twilio_whatsapp_from": settings.twilio_whatsapp_from,
        "allow_http_domains": list(settings.allow_http_domains),
    }
    logs_text = ""
    if include_logs:
        logs = system_tools.read_log("app.log", 120)
        if logs.get("ok"):
            logs_text = "\n".join(logs.get("lines", [])[-120:])
    health = {}
    if include_health:
        vm = psutil.virtual_memory()
        du = psutil.disk_usage("/")
        health = {
            "cpu_percent": psutil.cpu_percent(interval=0.0),
            "memory_percent": vm.percent,
            "disk_percent": du.percent,
            "python": platform.python_version(),
        }
    tools = []
    if include_tools:
        tools = [t["function"] for t in tool_schemas()]

    client = OpenAI()
    system = (
        "You are an admin UI assistant for WotBot. Explain settings clearly and concisely. "
        "Never request or reveal secrets. Use short paragraphs and bullets."
    )
    msgs = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": f"Question: {q}\n\nConfig: {cfg}\nHealth: {health}\nTools: {[t.get('name') for t in tools]}\nLogs(last):\n{logs_text[-2000:]}",
        },
    ]
    try:
        resp = client.chat.completions.create(model=settings.openai_model, messages=msgs, temperature=0.3, max_tokens=400)
        answer = resp.choices[0].message.content or "(no content)"
        return {"ok": True, "answer": answer}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/ai/summarize-logs")
def api_ai_summarize_logs(_: bool = Depends(require_auth), payload: Dict = Body(default={})):  # type: ignore[assignment]
    lines = int((payload or {}).get("lines") or 300)
    lines = max(50, min(1000, lines))
    logs = system_tools.read_log("app.log", lines)
    if not logs.get("ok"):
        return JSONResponse({"ok": False, "error": logs.get("error", "log read failed")}, status_code=500)
    text = "\n".join(logs.get("lines", []))
    client = OpenAI()
    prompt = (
        "Summarize the following application logs. Focus on:\n"
        "- Errors, exceptions, tracebacks (with probable causes)\n"
        "- Warnings and intermittent failures\n"
        "- Recent successful operations\n"
        "Respond with short bullet points suitable for an admin."
    )
    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.2,
            max_tokens=400,
            messages=[
                {"role": "system", "content": "You are a helpful SRE summarizer."},
                {"role": "user", "content": f"{prompt}\n\nLogs (last {lines} lines):\n{text[-8000:]}"},
            ],
        )
        answer = resp.choices[0].message.content or "(no summary)"
        return {"ok": True, "summary": answer}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/twilio/test-send")
def api_twilio_test_send(_: bool = Depends(require_auth), payload: Dict = Body(...)):
    to = (payload or {}).get("to", "").strip()
    message = (payload or {}).get("message", "Test: hello from WotBot").strip()
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        return JSONResponse({"ok": False, "error": "Twilio credentials not configured"}, status_code=400)
    if not settings.twilio_whatsapp_from:
        return JSONResponse({"ok": False, "error": "TWILIO_WHATSAPP_FROM not set"}, status_code=400)
    if not to:
        return JSONResponse({"ok": False, "error": "Missing 'to'"}, status_code=400)
    if not to.startswith("whatsapp:"):
        to = f"whatsapp:{to}"
    try:
        from twilio.rest import Client as TwilioClient

        client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        msg = client.messages.create(body=message[:1400], from_=settings.twilio_whatsapp_from, to=to)
        return {"ok": True, "sid": msg.sid, "status": getattr(msg, 'status', None)}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/mcp/list-tools")
def api_mcp_list_tools(server: str | None = Body(default=None), _: bool = Depends(require_auth)):
    # If server provided, list that one; else list all
    try:
        if server:
            # resolve server by index or URL
            servers = list(settings.mcp_servers)
            chosen = None
            try:
                idx = int(server)
                if 0 <= idx < len(servers):
                    chosen = servers[idx]
            except Exception:
                pass
            if chosen is None:
                for s in servers:
                    if s.rstrip('/') == server.rstrip('/'):
                        chosen = s
                        break
            if chosen is None:
                return JSONResponse({"ok": False, "error": f"Unknown MCP server: {server}"}, status_code=400)
            if urlparse(chosen).scheme in ("http", "https"):
                client = mcp_client.MCPHttpClient(chosen, settings.mcp_token)
                res = client.list_tools()
            else:
                # Treat as local exec command (split by whitespace)
                cmd = chosen.split()
                res = MCPExecClient(cmd).list_tools()
            return res
        else:
            return mcp_client.mcp_list_all()
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/mcp/validate")
def api_mcp_validate(server: str = Body(...), _: bool = Depends(require_auth)):
    try:
        servers = list(settings.mcp_servers)
        chosen = None
        # Allow index or URL
        try:
            idx = int(server)
            if 0 <= idx < len(servers):
                chosen = servers[idx]
        except Exception:
            pass
        if chosen is None:
            for s in servers:
                if s.rstrip('/') == server.rstrip('/'):
                    chosen = s
                    break
        if chosen is None:
            # Try validating the given URL directly without being in settings
            chosen = server
        if urlparse(chosen).scheme in ("http", "https"):
            client = mcp_client.MCPHttpClient(chosen, settings.mcp_token)
            res = client.list_tools()
        else:
            cmd = chosen.split()
            res = MCPExecClient(cmd).list_tools()
        if res.get("ok"):
            return {"ok": True, "server": chosen, "tools_count": len(res.get("result", []) if isinstance(res.get("result"), list) else [])}
        return JSONResponse({"ok": False, "server": chosen, "error": res.get("error")}, status_code=502)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/api/logs")
def api_logs(path: str = Query(default="app.log"), lines: int = Query(default=200, ge=1, le=1000), _: bool = Depends(require_auth)):
    return system_tools.read_log(path, lines)


@router.get("/api/config/export")
def api_config_export(_: bool = Depends(require_auth)):
    # Return the persisted overrides as JSON
    import json, os
    try:
        if os.path.exists(settings.overrides_path):
            with open(settings.overrides_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}
        return JSONResponse({"ok": True, "overrides": data})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/config/import")
def api_config_import(_: bool = Depends(require_auth), payload: dict = Body(...)):
    try:
        if not isinstance(payload, dict):
            return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)
        overrides = payload.get("overrides") if "overrides" in payload else payload
        if not isinstance(overrides, dict):
            return JSONResponse({"ok": False, "error": "Invalid overrides"}, status_code=400)
        apply_overrides(overrides)
        save_overrides(overrides)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# removed example MCP endpoint


@router.get("/api/tools")
def api_tools(_: bool = Depends(require_auth)):
    # Return both all tools and currently effective tools, plus enabled names
    all_defs = [t["function"] for t in all_tool_schemas()]
    eff_defs = [t["function"] for t in tool_schemas()]
    enabled = list(settings.enabled_tools) if settings.enabled_tools else []
    return {"ok": True, "all": all_defs, "effective": eff_defs, "enabled_names": enabled or ["*"]}


@router.post("/api/tools/enable")
def api_tools_enable(_: bool = Depends(require_auth), payload: dict | list = Body(...)):
    # Accept either {"all": true} or a list of names
    if isinstance(payload, dict) and payload.get("all") is True:
        overrides = {"ENABLED_TOOLS": "*"}
        names = [t["function"]["name"] for t in all_tool_schemas()]
    else:
        names = payload if isinstance(payload, list) else []
        if not isinstance(names, list):
            return JSONResponse({"ok": False, "error": "names must be list or {all:true}"}, status_code=400)
        overrides = {"ENABLED_TOOLS": ",".join(names) if names else ""}
    apply_overrides(overrides)
    save_overrides(overrides)
    return {"ok": True, "enabled": names}
