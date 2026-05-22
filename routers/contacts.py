"""
Emergency contacts CRUD — used by Flutter settings screen.
"""
from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.supabase_service import get_supabase_client

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


class ContactIn(BaseModel):
    user_id: str
    name: str
    phone: str
    relationship: str
    is_primary: bool = False


@router.get("")
async def list_contacts(user_id: str) -> list[dict]:
    db = get_supabase_client()
    if not db:
        return []
    try:
        r = (
            db.table("emergency_contacts")
            .select("*")
            .eq("user_id", user_id)
            .order("is_primary", desc=True)
            .order("created_at")
            .execute()
        )
        return r.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def add_contact(body: ContactIn) -> dict:
    db = get_supabase_client()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        row = {
            "id": str(_uuid.uuid4()),
            "user_id": body.user_id,
            "name": body.name,
            "phone": body.phone,
            "relationship": body.relationship,
            "is_primary": body.is_primary,
        }
        r = db.table("emergency_contacts").insert(row).execute()
        return r.data[0] if r.data else row
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{contact_id}")
async def delete_contact(contact_id: str) -> dict:
    db = get_supabase_client()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        db.table("emergency_contacts").delete().eq("id", contact_id).execute()
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{contact_id}/primary")
async def set_primary(contact_id: str, user_id: str) -> dict:
    db = get_supabase_client()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        db.table("emergency_contacts").update({"is_primary": False}).eq("user_id", user_id).execute()
        db.table("emergency_contacts").update({"is_primary": True}).eq("id", contact_id).execute()
        return {"updated": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
