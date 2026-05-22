"""
Medicine CRUD + OCR router.
"""
from __future__ import annotations

import io
import re
import uuid as _uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel

from services.supabase_service import get_supabase_client

router = APIRouter(prefix="/api/medicine", tags=["medicine"])


# ── OCR ──────────────────────────────────────────────────────────

def _extract_with_tesseract(image: Image.Image) -> list[str]:
    try:
        import pytesseract
        text = pytesseract.image_to_string(image, lang="eng")
        return _parse_medicine_names(text)
    except Exception:
        return []


def _parse_medicine_names(text: str) -> list[str]:
    pattern = re.compile(
        r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s*"
        r"(?:\d+\s*(?:mg|ml|mcg|IU|tablet|cap|tabs))?",
        re.IGNORECASE,
    )
    candidates: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = pattern.search(line)
        if match:
            name = match.group(1).strip()
            if 2 < len(name) < 60 and name not in candidates:
                candidates.append(name)
    return candidates[:10]


@router.post("/ocr")
async def medicine_ocr(image: UploadFile = File(...)) -> dict:
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Upload must be an image file.")
    raw = await image.read()
    try:
        pil_image = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not decode image.")
    w, h = pil_image.size
    if w < 800:
        scale = 800 / w
        pil_image = pil_image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    medicines = _extract_with_tesseract(pil_image)
    return {"medicines": medicines, "count": len(medicines)}


# ── CRUD ─────────────────────────────────────────────────────────

class MedicineIn(BaseModel):
    user_id: str
    name: str
    dosage: str = ""
    frequency: str = "morning"
    stock_count: int = 30
    daily_consumption: int = 1
    refill_threshold: int = 7
    pharmacy_contact: str | None = None


@router.get("/list")
async def list_medicines(user_id: str) -> list[dict]:
    db = get_supabase_client()
    if not db:
        return []
    try:
        r = (
            db.table("medicines")
            .select("*")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .order("created_at")
            .execute()
        )
        return r.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add")
async def add_medicine(body: MedicineIn) -> dict:
    db = get_supabase_client()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        row = {
            "id": str(_uuid.uuid4()),
            "user_id": body.user_id,
            "name": body.name,
            "dosage": body.dosage,
            "frequency": body.frequency,
            "stock_count": body.stock_count,
            "daily_consumption": body.daily_consumption,
            "refill_threshold": body.refill_threshold,
            "pharmacy_contact": body.pharmacy_contact,
            "is_active": True,
        }
        r = db.table("medicines").insert(row).execute()
        return r.data[0] if r.data else row
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{medicine_id}/take")
async def mark_taken(medicine_id: str, user_id: str) -> dict:
    db = get_supabase_client()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        r = db.table("medicines").select("stock_count").eq("id", medicine_id).execute()
        if not r.data:
            raise HTTPException(status_code=404, detail="Medicine not found")
        current = r.data[0]["stock_count"]
        new_stock = max(0, current - 1)
        db.table("medicines").update({"stock_count": new_stock}).eq("id", medicine_id).execute()
        db.table("medicine_logs").insert({
            "id": str(_uuid.uuid4()),
            "medicine_id": medicine_id,
            "user_id": user_id,
            "status": "taken",
            "scheduled_time": _now_iso(),
            "actual_time": _now_iso(),
        }).execute()
        return {"stock_count": new_stock}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{medicine_id}")
async def delete_medicine(medicine_id: str) -> dict:
    db = get_supabase_client()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        db.table("medicines").update({"is_active": False}).eq("id", medicine_id).execute()
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
