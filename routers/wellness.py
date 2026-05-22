"""
Wellness router — check-in analysis, logs CRUD, trend.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.llm_service import analyze_sentiment
from services.supabase_service import get_supabase_client

router = APIRouter(prefix="/api/wellness", tags=["wellness"])


def _to_int(v, default: int = 3) -> int:
    if isinstance(v, int):
        return v
    try:
        return int(v)
    except (ValueError, TypeError):
        return default


# ── Analyze (AI sentiment) ────────────────────────────────────────

class WellnessCheckIn(BaseModel):
    user_id: str
    mood_score: int = Field(ge=1, le=5)
    sleep_quality: int = Field(ge=1, le=5)
    pain_level: int = Field(ge=1, le=5)
    appetite: int = Field(ge=1, le=5)
    notes: str = ""


class WellnessAnalysisResponse(BaseModel):
    sentiment_score: float
    alert_triggered: bool
    summary: str


@router.post("/analyze", response_model=WellnessAnalysisResponse)
async def analyze(body: WellnessCheckIn) -> WellnessAnalysisResponse:
    text = (
        f"Mood: {body.mood_score}/5, Sleep: {body.sleep_quality}/5, "
        f"Pain: {body.pain_level}/5, Appetite: {body.appetite}/5. "
        f"Notes: {body.notes}"
    )
    score, alert = await analyze_sentiment(text)
    mood_labels = {1: "very low", 2: "low", 3: "okay", 4: "good", 5: "great"}
    summary = f"Mood is {mood_labels.get(body.mood_score, 'unknown')}. Pain level {body.pain_level}/5."
    if alert:
        summary += " Family notified."
    return WellnessAnalysisResponse(sentiment_score=score, alert_triggered=alert, summary=summary)


# ── Log CRUD ─────────────────────────────────────────────────────

class WellnessLogIn(BaseModel):
    user_id: str
    mood_score: int = Field(ge=1, le=5)
    sleep_quality: int = Field(ge=1, le=5)
    pain_level: int = Field(ge=0, le=10)
    appetite: int = Field(ge=1, le=5)
    notes: str = ""


@router.get("/logs")
async def get_logs(user_id: str, days: int = 30) -> list[dict]:
    db = get_supabase_client()
    if not db:
        return []
    try:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        r = (
            db.table("wellness_logs")
            .select("*")
            .eq("user_id", user_id)
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(30)
            .execute()
        )
        rows = r.data or []
        # Normalise sleep_quality and appetite to int in case DB stored as text
        for row in rows:
            row["sleep_quality"] = _to_int(row.get("sleep_quality"), 3)
            row["appetite"] = _to_int(row.get("appetite"), 3)
        return rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/log")
async def save_log(body: WellnessLogIn) -> dict:
    db = get_supabase_client()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        row = {
            "id": str(_uuid.uuid4()),
            "user_id": body.user_id,
            "mood_score": body.mood_score,
            "sleep_quality": body.sleep_quality,
            "pain_level": body.pain_level,
            "appetite": body.appetite,
            "notes": body.notes or None,
            "alert_triggered": False,
        }
        r = db.table("wellness_logs").insert(row).execute()
        saved = r.data[0] if r.data else row
        saved["sleep_quality"] = _to_int(saved.get("sleep_quality"), 3)
        saved["appetite"] = _to_int(saved.get("appetite"), 3)
        return saved
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/log/{log_id}")
async def delete_log(log_id: str) -> dict:
    db = get_supabase_client()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        db.table("wellness_logs").delete().eq("id", log_id).execute()
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Trend (placeholder) ───────────────────────────────────────────

@router.get("/trend")
async def trend(user_id: str, days: int = 7) -> dict:
    return {"user_id": user_id, "days": days, "message": "Query /api/wellness/logs directly."}
