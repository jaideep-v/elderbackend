"""
Builds a structured, token-efficient context string from the user's Supabase data.
Injected into Mistral's system prompt so the AI can give personalised answers.

Cache: 5-minute per-user TTL to avoid a Supabase round-trip on every message.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from config import settings

# ── In-process context cache ─────────────────────────────────────

_CACHE_TTL = 300  # seconds
_cache: dict[str, tuple[float, str]] = {}   # user_id → (timestamp, context_str)


_sb_client = None


def _supabase_client():
    global _sb_client
    if _sb_client is not None:
        return _sb_client
    if not settings.supabase_url or not settings.supabase_service_key:
        return None
    try:
        from supabase import create_client  # type: ignore
        _sb_client = create_client(settings.supabase_url, settings.supabase_service_key)
        return _sb_client
    except Exception:
        return None


# ── Individual fetchers ───────────────────────────────────────────

def _fetch(client, table: str, query_fn) -> list[dict[str, Any]]:
    """Run a Supabase query and return data, or [] on any error."""
    try:
        result = query_fn(client.table(table))
        return result.execute().data or []
    except Exception as exc:
        print(f"[context] {table} fetch failed: {exc}")
        return []


def _fetch_medicines(client, user_id: str) -> list[dict]:
    return _fetch(
        client, "medicines",
        lambda t: t.select(
            "id,name,dosage,frequency,stock_count,daily_consumption,"
            "refill_threshold,pharmacy_contact,is_active"
        ).eq("user_id", user_id).eq("is_active", True),
    )


def _fetch_reminders(client, user_id: str) -> list[dict]:
    today = datetime.now(timezone.utc).date().isoformat()
    month_ahead = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
    return _fetch(
        client, "reminders",
        lambda t: t.select(
            "title,date,type,is_recurring,recur_pattern,auto_greeting,contact_number"
        ).eq("user_id", user_id).gte("date", today).lte("date", month_ahead).order("date"),
    )


def _fetch_wellness(client, user_id: str) -> list[dict]:
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    return _fetch(
        client, "wellness_logs",
        lambda t: t.select(
            "mood_score,sleep_quality,pain_level,appetite,notes,created_at"
        ).eq("user_id", user_id).gte("created_at", week_ago).order("created_at", desc=True).limit(7),
    )


def _fetch_contacts(client, user_id: str) -> list[dict]:
    return _fetch(
        client, "emergency_contacts",
        lambda t: t.select(
            "name,phone,relationship,is_primary"
        ).eq("user_id", user_id).order("is_primary", desc=True),
    )


def _fetch_today_logs(client, user_id: str) -> list[dict]:
    """Medicine intake logs for today — for double-dose awareness."""
    today_start = datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    return _fetch(
        client, "medicine_logs",
        lambda t: t.select(
            "medicine_id,status,actual_time"
        ).eq("user_id", user_id)
         .gte("actual_time", today_start)
         .eq("status", "taken")
         .order("actual_time", desc=True),
    )


# ── Context formatter ─────────────────────────────────────────────

def _format(medicines: list, reminders: list, wellness: list, contacts: list,
            today_logs: list) -> str:
    now_str = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
    lines: list[str] = [f"=== USER DATA (as of {now_str}) ===\n"]

    # ── Medicines ────────────────────────────────────────────────
    lines.append(f"MEDICINES ({len(medicines)} active):")
    if not medicines:
        lines.append("  None added yet.")
    for m in medicines:
        daily = max(m.get("daily_consumption") or 1, 1)
        stock = m.get("stock_count", 0)
        threshold = m.get("refill_threshold", 7)
        days_left = stock // daily
        flag = " ⚠️LOW-STOCK" if days_left <= threshold else ""
        pharmacy = m.get("pharmacy_contact") or "not set"
        lines.append(
            f"  • {m['name']} {m.get('dosage','')} — {m.get('frequency','').upper()}"
            f" | stock {stock} units ({days_left}d left){flag}"
            f" | pharmacy: {pharmacy}"
        )

    # ── Today's doses taken ──────────────────────────────────────
    taken_ids = {log["medicine_id"] for log in today_logs}
    lines.append(f"\nTODAY'S DOSES TAKEN ({len(today_logs)} so far):")
    if not today_logs:
        lines.append("  No medicines logged as taken today.")
    else:
        for log in today_logs:
            taken_at = log.get("actual_time", "")
            # Format to readable HH:MM
            try:
                taken_at = taken_at[11:16]
            except Exception:
                pass
            # Find medicine name from medicines list
            med_name = next(
                (m["name"] for m in medicines if m.get("id") == log.get("medicine_id")),
                f"[id:{log.get('medicine_id','?')}]"
            )
            lines.append(f"  ✅ {med_name} — taken at {taken_at}")
    if medicines and taken_ids:
        not_yet = [m["name"] for m in medicines if m.get("id") not in taken_ids]
        if not_yet:
            lines.append(f"  ⏳ Not yet taken today: {', '.join(not_yet)}")

    # ── Reminders ────────────────────────────────────────────────
    lines.append(f"\nUPCOMING REMINDERS (next 30 days, {len(reminders)} total):")
    if not reminders:
        lines.append("  None scheduled.")
    for r in reminders:
        date_str = r.get("date", "")[:10]
        # days until
        try:
            delta = (datetime.fromisoformat(date_str) - datetime.now()).days
            when = "TODAY" if delta == 0 else f"in {delta}d"
        except Exception:
            when = date_str
        greet_note = ""
        if r.get("auto_greeting") and r.get("contact_number"):
            greet_note = f" [auto-greet → {r['contact_number']}]"
        recur_note = f" [{r.get('recur_pattern','yearly')}]" if r.get("is_recurring") else ""
        lines.append(
            f"  • [{r.get('type','custom').upper()}] {r['title']} — {when}{greet_note}{recur_note}"
        )

    # ── Wellness ─────────────────────────────────────────────────
    lines.append(f"\nWELLNESS (last 7 days, {len(wellness)} logs):")
    if not wellness:
        lines.append("  No wellness data yet.")
    else:
        moods = [w["mood_score"] for w in wellness if w.get("mood_score")]
        avg_mood = sum(moods) / len(moods) if moods else 0
        lines.append(f"  Average mood: {avg_mood:.1f}/5")
        for w in wellness:
            day = w.get("created_at", "")[:10]
            lines.append(
                f"  • {day}: mood={w.get('mood_score','?')}/5 "
                f"sleep={w.get('sleep_quality','?')}/5 "
                f"pain={w.get('pain_level','?')}/5 "
                f"appetite={w.get('appetite','?')}/5"
                + (f" | notes: {w['notes']}" if w.get("notes") else "")
            )

    # ── Emergency contacts ───────────────────────────────────────
    lines.append(f"\nEMERGENCY CONTACTS ({len(contacts)}):")
    if not contacts:
        lines.append("  None added yet.")
    for c in contacts:
        primary = " [PRIMARY]" if c.get("is_primary") else ""
        lines.append(
            f"  • {c['name']} ({c.get('relationship','other')}) — {c['phone']}{primary}"
        )

    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────

async def build_user_context(user_id: str) -> str:
    """
    Returns a formatted context string for the LLM system prompt.
    Uses a 5-minute in-process cache. Returns empty string on any failure.
    """
    # Cache hit
    cached = _cache.get(user_id)
    if cached and (time.time() - cached[0]) < _CACHE_TTL:
        return cached[1]

    client = _supabase_client()
    if client is None:
        return ""   # Supabase not configured — chat still works without context

    try:
        medicines  = _fetch_medicines(client, user_id)
        reminders  = _fetch_reminders(client, user_id)
        wellness   = _fetch_wellness(client, user_id)
        contacts   = _fetch_contacts(client, user_id)
        today_logs = _fetch_today_logs(client, user_id)

        context = _format(medicines, reminders, wellness, contacts, today_logs)
        _cache[user_id] = (time.time(), context)
        return context
    except Exception as exc:
        print(f"[context] build_user_context failed for {user_id}: {exc}")
        return ""


def invalidate_cache(user_id: str) -> None:
    """Call this after any write that changes user data."""
    _cache.pop(user_id, None)
