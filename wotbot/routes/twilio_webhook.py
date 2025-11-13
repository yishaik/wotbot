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

    if not from_number:
        return PlainTextResponse("Missing From", status_code=400)

    log.info("Incoming WhatsApp message from %s: %s", from_number, text[:200])

    # Process asynchronously, respond immediately to Twilio
    background.add_task(process_and_reply, from_number, text)

    # Return 204 No Content to avoid sending a stray message back to WhatsApp
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
