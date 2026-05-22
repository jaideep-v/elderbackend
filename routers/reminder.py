"""
Reminder router — CRUD + auto-greeting WhatsApp.
"""
from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.alert_service import send_whatsapp
from services.supabase_service import get_supabase_client

router = APIRouter(prefix="/api/reminder", tags=["reminders"])


# ── CRUD ─────────────────────────────────────────────────────────

class ReminderIn(BaseModel):
    user_id: str
    title: str
    date: str                  # ISO8601 datetime string
    type: str = "custom"
    is_recurring: bool = False
    recur_pattern: str | None = None
    auto_greeting: bool = False
    contact_number: str | None = None


@router.get("/list")
async def list_reminders(user_id: str) -> list[dict]:
    db = get_supabase_client()
    if not db:
        return []
    try:
        r = (
            db.table("reminders")
            .select("*")
            .eq("user_id", user_id)
            .order("date")
            .execute()
        )
        return r.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add")
async def add_reminder(body: ReminderIn) -> dict:
    db = get_supabase_client()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        row = {
            "id": str(_uuid.uuid4()),
            "user_id": body.user_id,
            "title": body.title,
            "date": body.date,
            "type": body.type,
            "is_recurring": body.is_recurring,
            "recur_pattern": body.recur_pattern,
            "auto_greeting": body.auto_greeting,
            "contact_number": body.contact_number,
        }
        r = db.table("reminders").insert(row).execute()
        return r.data[0] if r.data else row
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{reminder_id}")
async def delete_reminder(reminder_id: str) -> dict:
    db = get_supabase_client()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        db.table("reminders").delete().eq("id", reminder_id).execute()
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Auto-greeting ─────────────────────────────────────────────────

class GreetRequest(BaseModel):
    user_id: str
    reminder_title: str
    reminder_type: str
    contact_number: str
    contact_name: str = ""
    sender_name: str = "Family"


_TEMPLATES: dict[str, str] = {
    "birthday": "Happy Birthday{name_part}! Wishing you a wonderful day. Warm wishes from {sender}!",
    "anniversary": "Happy Anniversary{name_part}! Celebrating your beautiful journey. With love from {sender}!",
    "appointment": "Reminder{name_part}: You have an appointment today — '{title}'. Take care! From {sender}.",
    "custom": "A warm reminder{name_part}: '{title}'. Thinking of you! From {sender}.",
}


def _build_message(req: GreetRequest) -> str:
    template = _TEMPLATES.get(req.reminder_type, _TEMPLATES["custom"])
    name_part = f" {req.contact_name}" if req.contact_name else ""
    return template.format(name_part=name_part, title=req.reminder_title, sender=req.sender_name)


@router.post("/greet")
async def send_greeting(body: GreetRequest) -> dict:
    message = _build_message(body)
    ok = send_whatsapp(phone=body.contact_number, message=message)
    return {
        "sent": ok,
        "to": body.contact_number,
        "message_preview": message[:80] + ("..." if len(message) > 80 else ""),
    }
