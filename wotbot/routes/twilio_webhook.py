import logging
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from twilio.request_validator import RequestValidator

from ..config import settings
from ..conversation.session_store import SessionStore
from ..conversation.engine import ConversationEngine
from ..utils.twilio_utils import send_whatsapp_messages
import base64
import requests


log = logging.getLogger(__name__)
router = APIRouter()


_sessions = SessionStore()
_engine = ConversationEngine(_sessions)


def _twilio_signature_valid(request: Request, form_dict: Dict[str, str]) -> bool:
    if not settings.twilio_validate_signature:
        return True
    validator = RequestValidator(settings.twilio_auth_token)
    url = settings.public_base_url.rstrip("/") + str(request.url.path)
    signature = request.headers.get("X-Twilio-Signature", "")
    try:
        return validator.validate(url, dict(form_dict), signature)
    except Exception:
        return False


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request, background: BackgroundTasks):
    form = await request.form()
    if not _twilio_signature_valid(request, form):
        log.warning("Twilio signature invalid")
        return Response(status_code=status.HTTP_403_FORBIDDEN)
    from_number = form.get("From") or form.get("from")
    text = form.get("Body") or form.get("body") or ""
    num_media = int(form.get("NumMedia", "0") or 0)

    if not from_number:
        return PlainTextResponse("Missing From", status_code=400)

    log.info("Incoming WhatsApp message from %s: %s", from_number, text[:200])

    # Build content parts: start with text, then any image media as data URLs
    parts = []
    if text:
        parts.append({"type": "text", "text": text})
    if num_media > 0:
        for i in range(min(num_media, 5)):
            ctype = form.get(f"MediaContentType{i}") or ""
            url = form.get(f"MediaUrl{i}") or ""
            if not url:
                continue
            if not ctype.startswith("image/"):
                log.info("Ignoring non-image media %s", ctype)
                continue
            try:
                # Fetch media using Twilio basic auth
                resp = requests.get(url, auth=(settings.twilio_account_sid, settings.twilio_auth_token), timeout=10)
                resp.raise_for_status()
                data_b64 = base64.b64encode(resp.content).decode("ascii")
                data_url = f"data:{ctype};base64,{data_b64}"
                parts.append({"type": "image_url", "image_url": {"url": data_url}})
            except Exception as e:
                log.warning("Failed to fetch media %s: %s", url, e)

    # Process asynchronously, respond immediately to Twilio
    background.add_task(process_and_reply_parts, from_number, parts)

    # Twilio expects a 2xx quickly; return no content to avoid extra 'OK' message
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def process_and_reply(from_number: str, text: str):
    try:
        replies = _engine.converse(from_number, text)
    except Exception as e:
        log.exception("Error processing message: %s", e)
        replies = ["Sorry, an error occurred while processing your message."]
    try:
        send_whatsapp_messages(from_number, replies)
    except Exception:
        log.exception("Failed to send WhatsApp replies")


def process_and_reply_parts(from_number: str, parts):
    try:
        replies = _engine.converse_parts(from_number, parts)
    except Exception as e:
        log.exception("Error processing message with parts: %s", e)
        replies = ["Sorry, an error occurred while processing your message."]
    try:
        send_whatsapp_messages(from_number, replies)
    except Exception:
        log.exception("Failed to send WhatsApp replies")
