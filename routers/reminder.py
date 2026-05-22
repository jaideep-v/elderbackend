"""
Reminder router — handles auto-greeting WhatsApp messages for special occasions
(birthdays, anniversaries, appointments).

The Flutter app stores reminder data in Supabase directly.
This endpoint is called when a reminder fires and auto_greeting=true.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from services.alert_service import send_whatsapp

router = APIRouter(prefix="/api/reminder", tags=["reminders"])


class GreetRequest(BaseModel):
    user_id: str
    reminder_title: str           # e.g. "Grandson's Birthday"
    reminder_type: str            # 'birthday' | 'anniversary' | 'appointment' | 'custom'
    contact_number: str           # E.164 phone number to greet
    contact_name: str = ""        # optional — personalises message
    sender_name: str = "Family"   # name of the elder (from settingsProvider)


_TEMPLATES: dict[str, str] = {
    "birthday": (
        "🎂 Happy Birthday{name_part}! "
        "Wishing you a wonderful day filled with joy and love. "
        "Warm wishes from {sender}! 🎉"
    ),
    "anniversary": (
        "💕 Happy Anniversary{name_part}! "
        "Celebrating your beautiful journey together. "
        "With love from {sender}! 🌹"
    ),
    "appointment": (
        "📅 Reminder{name_part}: You have an appointment today — '{title}'. "
        "Take care and stay well! From {sender}. 💙"
    ),
    "custom": (
        "💌 A warm reminder{name_part}: '{title}'. "
        "Thinking of you! From {sender}. 🙏"
    ),
}


def _build_message(req: GreetRequest) -> str:
    template = _TEMPLATES.get(req.reminder_type, _TEMPLATES["custom"])
    name_part = f" {req.contact_name}" if req.contact_name else ""
    return template.format(
        name_part=name_part,
        title=req.reminder_title,
        sender=req.sender_name,
    )


@router.post("/greet")
async def send_greeting(body: GreetRequest) -> dict:
    message = _build_message(body)
    ok = send_whatsapp(phone=body.contact_number, message=message)
    return {
        "sent": ok,
        "to": body.contact_number,
        "message_preview": message[:80] + ("…" if len(message) > 80 else ""),
    }
