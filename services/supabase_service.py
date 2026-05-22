"""
Thin async wrapper for Supabase queries needed by the backend.
Uses the supabase-py client with the service role key (bypasses RLS).
Falls back gracefully if Supabase is not configured.
"""
from __future__ import annotations

from typing import Any

from config import settings


_cached_client = None


def _client():
    """Returns a singleton Supabase client or None if not configured."""
    global _cached_client
    if _cached_client is not None:
        return _cached_client
    if not settings.supabase_url or not settings.supabase_service_key:
        return None
    try:
        from supabase import create_client  # type: ignore
        _cached_client = create_client(settings.supabase_url, settings.supabase_service_key)
        return _cached_client
    except Exception:
        return None


def get_supabase_client():
    """Public accessor used by the agent action executor."""
    return _client()


def get_today_medicine_logs_sync(user_id: str) -> list[dict[str, Any]]:
    """
    Returns all medicine intake logs for today (synchronous, for safety checks).
    Each dict: {medicine_id, status, actual_time}
    """
    from datetime import datetime
    client = _client()
    if client is None:
        return []
    today_start = datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    try:
        result = (
            client.table("medicine_logs")
            .select("medicine_id, status, actual_time")
            .eq("user_id", user_id)
            .gte("actual_time", today_start)
            .eq("status", "taken")
            .order("actual_time", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as exc:
        print(f"[Supabase] get_today_medicine_logs_sync failed: {exc}")
        return []


async def get_emergency_contacts(user_id: str) -> list[dict[str, Any]]:
    """
    Returns list of emergency contact dicts for `user_id`.
    Each dict has at minimum: id, name, phone, relationship, is_primary.
    Returns [] if Supabase is not configured or query fails.
    """
    client = _client()
    if client is None:
        return []
    try:
        result = (
            client.table("emergency_contacts")
            .select("id, name, phone, relationship, is_primary")
            .eq("user_id", user_id)
            .order("is_primary", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as exc:
        print(f"[Supabase] get_emergency_contacts failed: {exc}")
        return []


async def get_reminders_with_greeting(user_id: str) -> list[dict[str, Any]]:
    """
    Returns reminders that have auto_greeting=true and have a contact_number set.
    Used by the reminder/greet endpoint.
    """
    client = _client()
    if client is None:
        return []
    try:
        result = (
            client.table("reminders")
            .select("id, title, date, contact_number")
            .eq("user_id", user_id)
            .eq("auto_greeting", True)
            .not_.is_("contact_number", "null")
            .execute()
        )
        return result.data or []
    except Exception as exc:
        print(f"[Supabase] get_reminders_with_greeting failed: {exc}")
        return []
