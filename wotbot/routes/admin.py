import base64
import logging
from typing import Dict

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..config import settings, apply_overrides, save_overrides
from ..tools import system_tools

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
def admin_index(_: bool = Depends(require_auth)):
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
        "message": "",
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
    TWILIO_ACCOUNT_SID: str = Form(default=""),
    TWILIO_AUTH_TOKEN: str = Form(default=""),
    TWILIO_WHATSAPP_FROM: str = Form(default=""),
    TWILIO_VALIDATE_SIGNATURE: str = Form(default="off"),
    PUBLIC_BASE_URL: str = Form(default=""),
    ALLOW_HTTP_DOMAINS: str = Form(default=""),
    ADMIN_PHONE_NUMBERS: str = Form(default=""),
):
    # Build overrides; for secrets, keep old if masked/empty
    overrides: Dict[str, str] = {}
    if OPENAI_API_KEY and not OPENAI_API_KEY.startswith("••••"):
        overrides["OPENAI_API_KEY"] = OPENAI_API_KEY.strip()
    if OPENAI_MODEL:
        overrides["OPENAI_MODEL"] = OPENAI_MODEL.strip()
    overrides["OPENAI_USE_ASSISTANTS"] = "true" if OPENAI_USE_ASSISTANTS == "on" else "false"
    overrides["OPENAI_ASSISTANT_ID"] = OPENAI_ASSISTANT_ID.strip()

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

    apply_overrides(overrides)
    save_overrides(overrides)

    # Redirect back to GET to avoid form resubmission
    return RedirectResponse(url=str(request.url), status_code=303)


@router.post("/restart")
def admin_restart(_: bool = Depends(require_auth)):
    res = system_tools.restart_self()
    return res

