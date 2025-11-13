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
from ..tools.schemas import tool_schemas, all_tool_schemas
from openai import OpenAI

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
        "OPENAI_USE_ASSISTANTS": settings.openai_use_assistants,
        "OPENAI_ASSISTANT_ID": settings.openai_assistant_id or "",
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
    OPENAI_ASSISTANT_ID: str = Form(default=""),
    ASSISTANT_INSTRUCTIONS: str = Form(default=""),
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
    overrides["OPENAI_ASSISTANT_ID"] = OPENAI_ASSISTANT_ID.strip()
    if ASSISTANT_INSTRUCTIONS:
        overrides["ASSISTANT_INSTRUCTIONS"] = ASSISTANT_INSTRUCTIONS

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
            client = mcp_client.MCPHttpClient(chosen, settings.mcp_token)
            res = client.list_tools()
            return res
        else:
            return mcp_client.mcp_list_all()
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


@router.post("/api/examples/add-local-mcp")
def api_examples_add_local_mcp(_: bool = Depends(require_auth)):
    # Adds the local example MCP server URL to MCP_SERVERS
    url = "http://127.0.0.1:9010/jsonrpc"
    servers = list(settings.mcp_servers)
    if url not in servers:
        servers.append(url)
    overrides = {"MCP_SERVERS": ",".join(servers)}
    apply_overrides(overrides)
    save_overrides(overrides)
    return {"ok": True, "servers": servers}


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
