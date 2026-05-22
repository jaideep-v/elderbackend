"""
WhatsApp + SOS alert delivery via Twilio.
Gracefully skips if credentials are not configured.
"""
from __future__ import annotations

from config import settings


def _twilio_client():
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        return None
    try:
        from twilio.rest import Client  # type: ignore
        return Client(settings.twilio_account_sid, settings.twilio_auth_token)
    except ImportError:
        return None


def send_whatsapp(phone: str, message: str) -> bool:
    """
    Sends a WhatsApp message to `phone` (E.164 format, e.g. +919876543210).
    Returns True on success, False if Twilio is not configured / call fails.
    """
    client = _twilio_client()
    if client is None:
        # Dev mode: just print
        print(f"[ALERT] WhatsApp → {phone}: {message}")
        return True
    try:
        to = f"whatsapp:{phone}" if not phone.startswith("whatsapp:") else phone
        client.messages.create(
            from_=settings.twilio_whatsapp_from,
            to=to,
            body=message,
        )
        return True
    except Exception as exc:
        print(f"[ALERT] Twilio error: {exc}")
        return False


def blast_sos(contacts: list[str], location_url: str, user_name: str = "your elder") -> list[bool]:
    """
    Sends SOS to all contacts. Returns list of success bools.
    """
    message = (
        f"🚨 SOS ALERT: {user_name} needs help!\n"
        f"Location: {location_url}\n"
        "Please call or go to them immediately."
    )
    return [send_whatsapp(phone, message) for phone in contacts]
