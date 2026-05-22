"""
Triggers the n8n low-stock alert workflow via webhook.
Fetches emergency contacts from Supabase and POSTs them to n8n.
"""
from __future__ import annotations

import httpx

from config import settings
from services.supabase_service import get_emergency_contacts


async def trigger_low_stock_alert(
    user_id: str,
    user_name: str,
    medicine_name: str,
    stock_count: int,
    days_remaining: int,
) -> None:
    """
    Fire-and-forget webhook to n8n when medicine stock is low.
    Does nothing if N8N_WEBHOOK_URL is not set (dev mode).
    """
    url = settings.n8n_webhook_url
    if not url:
        print(f"[n8n] Webhook URL not set — skipping low-stock alert for {medicine_name}")
        return

    contacts = await get_emergency_contacts(user_id)
    if not contacts:
        print(f"[n8n] No emergency contacts for user {user_id} — skipping alert")
        return

    payload = {
        "user_name": user_name,
        "medicine_name": medicine_name,
        "stock_count": stock_count,
        "days_remaining": days_remaining,
        "backend_url": f"http://localhost:8001",
        "contacts": [
            {
                "name": c["name"],
                "phone": c["phone"],
                "relationship": c.get("relationship", "family"),
            }
            for c in contacts
            if c.get("phone")
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            print(f"[n8n] Webhook response: {resp.status_code}")
    except Exception as exc:
        print(f"[n8n] Webhook call failed (non-blocking): {exc}")
