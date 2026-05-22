from __future__ import annotations

from agent.intent_detector import detect_intent
from agent.slot_filler import AgentSession, REQUIRED_SLOTS, INTENT_GREETINGS
from agent.action_executor import execute_action, fetch_news
from services.llm_client import call_llm
from services.context_builder import build_user_context, invalidate_cache
from services.prompts import get_contextual_prompt, get_voice_prompt

# Per-user in-memory sessions
_sessions: dict[str, AgentSession] = {}

_CONFIRM_YES = {"yes", "yeah", "yep", "ok", "okay", "confirm", "sure", "do it",
                "go ahead", "haan", "seri", "aam", "add it", "save it", "log it"}
_CONFIRM_NO  = {"no", "nope", "cancel", "stop", "never mind", "don't", "dont",
                "illa", "venda", "cancel it"}


async def process_agent_message(user_id: str, message: str, chat_history: list, *, voice_mode: bool = False) -> dict:
    """
    Returns:
        {response: str, action_taken: bool, active_intent: str | None}
    """
    session = _sessions.setdefault(user_id, AgentSession(user_id=user_id))
    low = message.lower().strip()

    # ── CASE 1: Awaiting yes/no confirmation ─────────────────────────────
    if session.pending_confirmation:
        if low in _CONFIRM_YES:
            result = await execute_action(session, user_id)
            intent_done = session.active_intent
            session.reset()
            invalidate_cache(user_id)   # Fresh context on next chat message
            return {"response": result, "action_taken": True, "active_intent": intent_done}
        if low in _CONFIRM_NO:
            session.reset()
            return {"response": "No problem, I've cancelled that. What else can I help with?",
                    "action_taken": False, "active_intent": None}
        return {"response": "I need a yes or no to proceed. Should I go ahead?",
                "action_taken": False, "active_intent": session.active_intent}

    # ── CASE 2: Already collecting slots ─────────────────────────────────
    if session.active_intent:
        # Allow user to cancel mid-flow
        if low in _CONFIRM_NO:
            session.reset()
            return {"response": "No problem, I've cancelled that. What else can I help with?",
                    "action_taken": False, "active_intent": None}
        next_slot = session.get_next_empty_slot()
        if next_slot:
            slot_name, slot_cfg = next_slot
            extracted = await _extract_slot(message, slot_name, slot_cfg)

            if extracted and low not in ("skip", "no", "none", "unknown"):
                session.collected_slots[slot_name] = extracted
            elif not slot_cfg["required"]:
                session.collected_slots[slot_name] = None  # skip optional
            else:
                return {"response": f"I didn't quite catch that. {slot_cfg['prompt']}",
                        "action_taken": False, "active_intent": session.active_intent}

            # Next empty slot? (auto-skip dependent optional slots)
            nxt = session.get_next_empty_slot()
            # Skip contact_number if auto_greeting was declined
            if nxt and nxt[0] == "contact_number":
                auto_greet = str(session.collected_slots.get("auto_greeting", "")).lower()
                if auto_greet in ("no", "none", "", "false"):
                    session.collected_slots["contact_number"] = None
                    nxt = session.get_next_empty_slot()
            if nxt:
                return {"response": nxt[1]["prompt"],
                        "action_taken": False, "active_intent": session.active_intent}
            # All filled → confirm
            session.pending_confirmation = True
            return {"response": session.confirmation_message(),
                    "action_taken": False, "active_intent": session.active_intent}

    # ── CASE 3: New message — detect intent ──────────────────────────────
    ctx_summary = " | ".join(
        f"{m['role']}: {m['content'][:50]}" for m in chat_history[-5:]
    )
    intent_data = await detect_intent(message, ctx_summary)
    intent     = intent_data.get("intent", "GENERAL_CHAT")
    confidence = float(intent_data.get("confidence", 0))
    entities   = intent_data.get("entities", {}) or {}

    # Guard: short greetings / filler should never trigger action intents
    _GREETINGS = {"hi", "hai", "hey", "hello", "hii", "hiii", "yo", "sup",
                  "good morning", "good evening", "good night", "thanks",
                  "thank you", "ok", "okay", "hmm", "bye", "hola", "namaste"}
    if low in _GREETINGS:
        intent = "GENERAL_CHAT"
        confidence = 0.0

    if intent in REQUIRED_SLOTS and confidence >= 0.55:
        session.active_intent      = intent
        session.collected_slots    = {}
        session.pending_confirmation = False

        # Pre-fill entities from the first message
        for slot_name in REQUIRED_SLOTS[intent]:
            val = entities.get(slot_name)
            if val and str(val).lower() not in ("null", "none", ""):
                session.collected_slots[slot_name] = val

        nxt = session.get_next_empty_slot()
        if nxt:
            greeting = INTENT_GREETINGS.get(intent, "Let me help you with that!")
            return {"response": f"{greeting}\n\n{nxt[1]['prompt']}",
                    "action_taken": False, "active_intent": intent}
        # Rare: all slots already in the first message
        session.pending_confirmation = True
        return {"response": session.confirmation_message(),
                "action_taken": False, "active_intent": intent}

    # ── CASE 3b: FETCH_NEWS — no slots, direct action ────────────────────
    if intent == "FETCH_NEWS" and confidence >= 0.55:
        session.reset()
        news_cat = entities.get("news_category")
        if news_cat and str(news_cat).lower() in ("null", "none", ""):
            news_cat = None
        result = await fetch_news(category=news_cat)
        return {"response": result, "action_taken": True, "active_intent": "FETCH_NEWS"}

    # ── CASE 4: General chat / queries ────────────────────────────────────
    session.reset()
    user_context  = await build_user_context(user_id)
    system_prompt = get_voice_prompt(user_context) if voice_mode else get_contextual_prompt(user_context)
    messages = [{"role": "system", "content": system_prompt}]
    for turn in chat_history[-10:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": message})
    reply = await call_llm(messages, max_tokens=150 if voice_mode else 300)
    return {"response": reply, "action_taken": False, "active_intent": None}


async def _extract_slot(message: str, slot_name: str, slot_cfg: dict) -> str | None:
    """
    Extract a slot value from the user's reply.
    Uses fast rule-based extraction for typed slots — avoids unreliable LLM output.
    Falls back to LLM only for free-text string slots.
    """
    import re
    msg = message.strip()
    low = msg.lower()
    slot_type = slot_cfg.get("type", "str")

    # ── Integer slots ────────────────────────────────────────────────
    if slot_type == "int":
        nums = re.findall(r"\d+", msg)
        return nums[0] if nums else None

    # ── Boolean slots ────────────────────────────────────────────────
    if slot_type == "bool":
        if any(w in low for w in ("yes", "yeah", "yep", "sure", "ok", "haan", "seri")):
            return "yes"
        if any(w in low for w in ("no", "nope", "skip", "never", "illa", "venda")):
            return "no"
        return None

    # ── Date slots ───────────────────────────────────────────────────
    if slot_type == "date":
        # Return the whole message — action_executor._parse_date handles it
        return msg if msg else None

    # ── Time/frequency slots (str but used for time) ─────────────────
    if slot_type == "time_list" or slot_name == "frequency":
        return msg if msg else None

    # ── Free-text string — use first clean line (no LLM call) ────────
    # Take only the first non-empty line and cap at 80 chars
    first_line = next((ln.strip() for ln in msg.splitlines() if ln.strip()), msg)
    return first_line[:80] if first_line else None
