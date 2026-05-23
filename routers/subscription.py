"""
Subscription plans — list plans and activate a plan for a user.
Payment is mocked for the hackathon demo.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.supabase_service import get_supabase_client

router = APIRouter(prefix="/api/subscription", tags=["subscription"])

PLANS = [
    {
        "id": "free",
        "name": "Free",
        "price_monthly": 0,
        "price_annual": 0,
        "currency": "INR",
        "tagline": "Essential safety for every elder",
        "features": [
            "AI Chat Companion",
            "Medicine Reminders",
            "Wellness Logging",
            "Shake-to-Call (local)",
            "News Digest (5 articles/day)",
            "Emergency Contacts",
        ],
        "locked_features": [
            "GPS SOS WhatsApp Alerts",
            "Health Dashboard",
            "Voice AI Assistant",
            "Unlimited News",
            "Wellness Analytics",
        ],
    },
    {
        "id": "premium",
        "name": "Premium",
        "price_monthly": 299,
        "price_annual": 2499,
        "currency": "INR",
        "tagline": "Complete peace of mind for families",
        "badge": "Most Popular",
        "features": [
            "Everything in Free",
            "GPS SOS WhatsApp Alerts",
            "Health Dashboard & Trends",
            "Voice AI Assistant",
            "Unlimited News Digest",
            "Wellness Analytics",
            "Priority Support",
        ],
        "locked_features": [],
    },
    {
        "id": "annual",
        "name": "Annual",
        "price_monthly": 208,
        "price_annual": 2499,
        "currency": "INR",
        "tagline": "Best value — 2 months free",
        "badge": "Best Value",
        "features": [
            "Everything in Premium",
            "2 Months Free vs Monthly",
            "Early Access to New Features",
            "Dedicated Support",
        ],
        "locked_features": [],
    },
]


class ActivateIn(BaseModel):
    user_id: str
    plan: str  # 'free' | 'premium' | 'annual'
    billing: str = "monthly"  # 'monthly' | 'annual'


@router.get("/plans")
async def list_plans() -> list[dict]:
    return PLANS


@router.post("/activate")
async def activate_plan(body: ActivateIn) -> dict:
    if body.plan not in ("free", "premium", "annual"):
        raise HTTPException(400, "Invalid plan")

    db = get_supabase_client()
    if not db:
        raise HTTPException(503, "Database unavailable")

    now = datetime.now(timezone.utc).isoformat()
    result = (
        db.table("users")
        .update({"plan": body.plan, "plan_activated_at": now})
        .eq("id", body.user_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "User not found")

    return {
        "success": True,
        "user_id": body.user_id,
        "plan": body.plan,
        "activated_at": now,
    }


@router.get("/status")
async def get_status(user_id: str) -> dict:
    db = get_supabase_client()
    if not db:
        raise HTTPException(503, "Database unavailable")

    result = db.table("users").select("plan,plan_activated_at").eq("id", user_id).execute()
    if not result.data:
        raise HTTPException(404, "User not found")

    row = result.data[0]
    return {
        "plan": row.get("plan", "free"),
        "plan_activated_at": row.get("plan_activated_at"),
        "is_premium": row.get("plan", "free") in ("premium", "annual"),
    }
