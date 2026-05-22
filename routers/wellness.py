from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.llm_service import analyze_sentiment

router = APIRouter(prefix="/api/wellness", tags=["wellness"])


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

    # Build a human-readable summary
    mood_labels = {1: "very low", 2: "low", 3: "okay", 4: "good", 5: "great"}
    summary = (
        f"Mood is {mood_labels.get(body.mood_score, 'unknown')}. "
        f"Pain level {body.pain_level}/5."
    )
    if alert:
        summary += " ⚠️ Family notified."

    return WellnessAnalysisResponse(
        sentiment_score=score,
        alert_triggered=alert,
        summary=summary,
    )


@router.get("/trend")
async def trend(user_id: str, days: int = 7) -> dict:
    # Placeholder — trend data is computed on the Flutter side from Supabase
    return {"user_id": user_id, "days": days, "message": "Query Supabase wellness_logs directly."}
