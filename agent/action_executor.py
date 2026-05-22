from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta

import httpx

from services.supabase_service import get_supabase_client
from services.context_builder import invalidate_cache
from services.n8n_service import trigger_low_stock_alert


async def execute_action(session, user_id: str) -> str:
    """Execute the confirmed action and return a human-readable result."""
    client = get_supabase_client()
    if client is None:
        return "Supabase is not configured — I can't save data right now. Please check the backend settings."

    intent = session.active_intent
    s = session.collected_slots

    try:
        # ── ADD MEDICINE ─────────────────────────────────────────────
        if intent == "ADD_MEDICINE":
            frequency = _parse_frequency(s.get("frequency", ""))
            stock = int(s.get("stock_count", 0))
            daily = int(s.get("daily_consumption", 1))
            client.table("medicines").insert({
                "user_id": user_id,
                "name": s["medicine_name"],
                "dosage": s.get("dosage", ""),
                "stock_count": stock,
                "frequency": json.dumps(frequency),
                "daily_consumption": daily,
                "refill_threshold": 5,
                "pharmacy_contact": s.get("pharmacy_contact") or None,
                "is_active": True,
            }).execute()
            days = stock // max(daily, 1)
            return (
                f"✅ Done! {s['medicine_name']} has been added to your medicines. "
                f"I'll remind you every day at {s.get('frequency', 'the scheduled time')}. "
                f"You have about {days} days of supply."
            )

        # ── DELETE MEDICINE ──────────────────────────────────────────
        if intent == "DELETE_MEDICINE":
            name = s["medicine_name"]
            res = (
                client.table("medicines")
                .update({"is_active": False})
                .eq("user_id", user_id)
                .ilike("name", f"%{name}%")
                .execute()
            )
            if res.data:
                return f"✅ {name} has been removed from your active medicines. No more reminders for it."
            return f"I couldn't find a medicine called '{name}'. Can you check the name?"

        # ── TAKE MEDICINE ────────────────────────────────────────────
        if intent == "TAKE_MEDICINE":
            name = s["medicine_name"]
            med_res = (
                client.table("medicines")
                .select("*")
                .eq("user_id", user_id)
                .ilike("name", f"%{name}%")
                .eq("is_active", True)
                .execute()
            )
            if not med_res.data:
                return f"I couldn't find '{name}' in your active medicines. Say 'what medicines do I take' to see your list."
            med = med_res.data[0]

            # ── SAFETY CHECK 1: Double-dose detection ─────────────────
            already = _check_double_dose(client, user_id, med["id"])
            if already:
                taken_at = already.get("actual_time", "")
                try:
                    taken_at = taken_at[11:16]   # HH:MM
                except Exception:
                    pass
                return (
                    f"🚨 Safety Alert! You already took {med['name']} today at {taken_at}.\n\n"
                    f"Taking it again could be harmful or cause a double dose. "
                    f"Please check your prescription carefully.\n\n"
                    f"If your doctor prescribed multiple doses per day, "
                    f"please verify the timing before taking it again. "
                    f"When in doubt, call your family member or doctor. 💙"
                )

            # ── SAFETY CHECK 2: Timing warning (advisory only) ─────────
            timing = _check_timing(med)
            timing_note = ""
            if timing:
                timing_note = (
                    f"\n\n⏰ Timing note: {med['name']} is usually scheduled at {timing['scheduled']}. "
                    f"You're taking it {timing['gap_hours']}h "
                    f"{'early' if timing['early'] else 'late'}. "
                    f"If your doctor changed the timing, that's fine — just making sure!"
                )

            # ── Safe to log ─────────────────────────────────────────
            new_stock = max(med["stock_count"] - med["daily_consumption"], 0)
            client.table("medicines").update({"stock_count": new_stock}).eq("id", med["id"]).execute()
            try:
                client.table("medicine_logs").insert({
                    "medicine_id": med["id"],
                    "user_id": user_id,
                    "status": "taken",
                    "scheduled_time": datetime.now().isoformat(),
                    "actual_time": datetime.now().isoformat(),
                }).execute()
            except Exception:
                pass
            days = new_stock // max(med["daily_consumption"], 1)
            msg = f"✅ {med['name']} marked as taken! Stock updated: {new_stock} remaining ({days} days)."
            if days <= med.get("refill_threshold", 5):
                msg += f"\n\n⚠️ Only {days} days of {med['name']} left! Consider refilling soon."
                # Fire-and-forget: trigger n8n workflow to alert son/doctor
                try:
                    await trigger_low_stock_alert(
                        user_id=user_id,
                        user_name="your elder",
                        medicine_name=med["name"],
                        stock_count=new_stock,
                        days_remaining=days,
                    )
                except Exception as exc:
                    print(f"[n8n] trigger_low_stock_alert failed (non-blocking): {exc}")
            msg += timing_note
            return msg

        # ── EDIT MEDICINE ────────────────────────────────────────────
        if intent == "EDIT_MEDICINE":
            name = s["medicine_name"]
            field_map = {
                "dosage": "dosage", "stock": "stock_count", "time": "frequency",
                "daily": "daily_consumption", "daily amount": "daily_consumption",
            }
            db_field = field_map.get(s.get("field_to_edit", "").lower(), s.get("field_to_edit"))
            new_val: object = s["new_value"]
            if db_field in ("stock_count", "daily_consumption"):
                new_val = int(str(new_val))
            if db_field == "frequency":
                new_val = json.dumps(_parse_frequency(str(new_val)))
            client.table("medicines").update({db_field: new_val}).eq("user_id", user_id).ilike("name", f"%{name}%").execute()
            return f"✅ Updated {name}'s {s.get('field_to_edit')} to {s['new_value']}."

        # ── ADD REMINDER ─────────────────────────────────────────────
        if intent == "ADD_REMINDER":
            auto = str(s.get("auto_greeting", "no")).lower() in ("yes", "true", "1", "haan")
            reminder_type = s.get("reminder_type", "custom")
            client.table("reminders").insert({
                "user_id": user_id,
                "title": s["reminder_title"],
                "type": _map_reminder_type(reminder_type),
                "date": _parse_date(s.get("reminder_date", "")),
                "auto_greeting": auto,
                "contact_number": s.get("contact_number") or None,
                "is_recurring": reminder_type.lower() in ("birthday", "anniversary"),
                "recur_pattern": "yearly" if reminder_type.lower() in ("birthday", "anniversary") else None,
            }).execute()
            return f"✅ Reminder saved! I'll remind you about '{s['reminder_title']}' on {s.get('reminder_date')}."

        # ── DELETE REMINDER ──────────────────────────────────────────
        if intent == "DELETE_REMINDER":
            title = s["reminder_title"]
            client.table("reminders").delete().eq("user_id", user_id).ilike("title", f"%{title}%").execute()
            return f"✅ Reminder for '{title}' has been removed."

        # ── ADD CONTACT ──────────────────────────────────────────────
        if intent == "ADD_CONTACT":
            primary = str(s.get("is_primary", "no")).lower() in ("yes", "true", "1")
            client.table("emergency_contacts").insert({
                "user_id": user_id,
                "name": s["contact_name"],
                "phone": s["contact_phone"],
                "relationship": s.get("contact_relationship", "other"),
                "is_primary": primary,
            }).execute()
            return f"✅ {s['contact_name']} ({s.get('contact_relationship')}) added as an emergency contact."

        # ── LOG WELLNESS ─────────────────────────────────────────────
        if intent == "LOG_WELLNESS":
            mood_map  = {"great": 5, "good": 4, "okay": 3, "ok": 3, "low": 2, "bad": 1}
            qual_map  = {"good": 5, "great": 5, "fair": 3, "okay": 3, "ok": 3, "poor": 1, "bad": 1}
            mood_score    = mood_map.get(str(s.get("mood", "")).lower(), 3)
            sleep_score   = qual_map.get(str(s.get("sleep", "")).lower(), 3)
            appetite_score = qual_map.get(str(s.get("appetite", "")).lower(), 3)
            client.table("wellness_logs").insert({
                "user_id":       user_id,
                "mood_score":    mood_score,
                "sleep_quality": sleep_score,
                "pain_level":    int(str(s.get("pain_level", 0))),
                "appetite":      appetite_score,
                "notes":         f"Logged via chat at {datetime.now().strftime('%I:%M %p')}",
            }).execute()
            if mood_score <= 2:
                return "✅ Wellness check-in logged! I notice you're not feeling great — it's okay to have tough days. Would you like me to notify your family?"
            return "✅ Wellness check-in logged! Glad to hear how you're doing. Keep it up! 💪"

    except Exception as exc:
        return f"Sorry, something went wrong: {exc}. Please try again or do it manually from the app."

    return "Action completed."


# ── Helpers ───────────────────────────────────────────────────────────────

def _check_double_dose(client, user_id: str, medicine_id: str) -> dict | None:
    """
    Returns the last intake log if this medicine was already taken today, else None.
    This is the primary safety guard against accidental double-dosing.
    """
    today_start = datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    try:
        result = (
            client.table("medicine_logs")
            .select("actual_time, status")
            .eq("user_id", user_id)
            .eq("medicine_id", medicine_id)
            .gte("actual_time", today_start)
            .eq("status", "taken")
            .order("actual_time", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception:
        return None  # Fail open — don't block if DB check fails


def _check_timing(medicine: dict) -> dict | None:
    """
    Returns timing info if current time is far from any scheduled dose window.
    A dose window is ±90 minutes around each scheduled time.
    Returns None if timing is acceptable.
    """
    try:
        freq_raw = medicine.get("frequency", "[]")
        freq = json.loads(freq_raw) if isinstance(freq_raw, str) else freq_raw
        if not freq:
            return None

        now = datetime.now()
        now_minutes = now.hour * 60 + now.minute

        best_gap = float("inf")
        closest_time = freq[0]

        for t in freq:
            parts = t.split(":")
            sched_minutes = int(parts[0]) * 60 + int(parts[1])
            gap = abs(sched_minutes - now_minutes)
            # Handle midnight wrap
            gap = min(gap, 1440 - gap)
            if gap < best_gap:
                best_gap = gap
                closest_time = t

        # Within ±90 minutes of any scheduled time → safe
        if best_gap <= 90:
            return None

        sched_parts = closest_time.split(":")
        sched_minutes_val = int(sched_parts[0]) * 60 + int(sched_parts[1])
        early = now_minutes < sched_minutes_val

        # Convert 24h → 12h AM/PM for display
        h, m = int(sched_parts[0]), int(sched_parts[1])
        period = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        scheduled_display = f"{h12}:{m:02d} {period}"

        now_h, now_m = now.hour, now.minute
        now_period = "AM" if now_h < 12 else "PM"
        now_h12 = now_h % 12 or 12
        now_display = f"{now_h12}:{now_m:02d} {now_period}"

        return {
            "scheduled": scheduled_display,
            "now": now_display,
            "gap_hours": round(best_gap / 60, 1),
            "early": early,
        }
    except Exception:
        return None  # Fail open — don't block if timing check fails

def _parse_frequency(freq: str) -> list[str]:
    # Multi-word keys must come before their sub-words (dict preserves insertion order in py3.7+)
    time_map = {
        "before breakfast": "07:30", "after breakfast": "09:00",
        "before lunch": "12:30", "after lunch": "14:30",
        "before dinner": "19:30", "after dinner": "21:30",
        "morning": "08:00", "afternoon": "14:00", "evening": "18:00", "night": "21:00",
    }
    low = freq.lower().strip()
    times = []
    for key, val in time_map.items():
        if key in low:
            times.append(val)
    if times:
        # Deduplicate while preserving order
        seen: set[str] = set()
        return [t for t in times if not (t in seen or seen.add(t))]  # type: ignore[func-returns-value]
    matches = re.findall(r"(\d{1,2}):?(\d{2})?\s*(am|pm)?", low, re.IGNORECASE)
    times = []
    for h, m, period in matches:
        hour, minute = int(h), int(m) if m else 0
        if period.lower() == "pm" and hour < 12:
            hour += 12
        elif period.lower() == "am" and hour == 12:
            hour = 0
        times.append(f"{hour:02d}:{minute:02d}")
    return times or ["08:00"]


def _parse_date(date_str: str) -> str:
    today = datetime.now()
    low = date_str.lower().strip()
    if "today" in low:
        return today.isoformat()
    if "tomorrow" in low:
        return (today + timedelta(days=1)).isoformat()
    if "next week" in low:
        return (today + timedelta(weeks=1)).isoformat()
    for fmt in ("%d %B", "%d %B %Y", "%B %d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(date_str.strip(), fmt)
            if parsed.year == 1900:
                parsed = parsed.replace(year=today.year)
                if parsed < today:
                    parsed = parsed.replace(year=today.year + 1)
            return parsed.isoformat()
        except ValueError:
            continue
    return today.isoformat()


def _map_reminder_type(t: str) -> str:
    mapping = {
        "birthday": "birthday", "bday": "birthday",
        "anniversary": "anniversary",
        "doctor": "appointment", "appointment": "appointment",
        "hospital": "appointment", "checkup": "appointment",
        "temple": "religious", "puja": "religious",
        "religious": "religious", "festival": "religious",
    }
    low = t.lower()
    for key, val in mapping.items():
        if key in low:
            return val
    return "custom"


_NEWSDATA_API_KEY = "pub_afcabc644519464ab311cda556951834"
_NEWSDATA_URL = "https://newsdata.io/api/1/latest"

_NEWS_CAT_MAP = {
    "health": "health", "sports": "sports", "business": "business",
    "technology": "technology", "science": "science", "politics": "politics",
    "entertainment": "entertainment", "domestic": "domestic",
    "local": "domestic", "weather": "environment", "environment": "environment",
    "world": "world", "education": "education",
}


async def fetch_news(category: str | None = None) -> str:
    """Fetch latest Indian news from NewsData.io and return formatted text."""
    params: dict[str, str] = {
        "apikey": _NEWSDATA_API_KEY,
        "country": "in",
        "language": "en",
    }
    if category:
        mapped = _NEWS_CAT_MAP.get(category.lower())
        if mapped:
            params["category"] = mapped

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(_NEWSDATA_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results") or []
        if not results:
            return "I couldn't find any news articles right now. Please try again later."

        lines = ["Here are the latest headlines from India:\n"]
        for i, article in enumerate(results[:7], 1):
            title = article.get("title") or "Untitled"
            source = article.get("source_name") or "Unknown"
            desc = article.get("description") or ""
            if desc:
                desc = desc[:150].strip()
                if len(article.get("description", "")) > 150:
                    desc += "..."

            lines.append(f"{i}. **{title}**")
            if desc:
                lines.append(f"   {desc}")
            lines.append(f"   — {source}\n")

        cat_label = category or "all"
        lines.append(f"Showing {cat_label} news from India. Ask me for a specific category like 'sports news' or 'health news'!")
        return "\n".join(lines)

    except Exception as exc:
        return f"Sorry, I couldn't fetch news right now: {exc}"
