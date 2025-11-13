import logging
from typing import List

from twilio.rest import Client

from ..config import settings

log = logging.getLogger(__name__)


def twilio_client() -> Client:
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise RuntimeError("Twilio credentials not configured")
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


def send_whatsapp_messages(to: str, messages: List[str]):
    client = twilio_client()
    for body in messages:
        log.info("Sending WhatsApp message to %s (%d chars)", to, len(body))
        client.messages.create(
            body=body,
            from_=settings.twilio_whatsapp_from,
            to=to,
        )

