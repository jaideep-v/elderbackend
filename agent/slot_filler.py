from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# ── Slot definitions per intent ────────────────────────────────────────────

REQUIRED_SLOTS: dict[str, dict[str, dict]] = {
    "ADD_MEDICINE": {
        "medicine_name":   {"prompt": "What's the name of the medicine?", "type": "str", "required": True},
        "dosage":          {"prompt": "What's the dosage? For example, 500mg or 1 tablet.", "type": "str", "required": True},
        "stock_count":     {"prompt": "How many tablets/pills do you have right now?", "type": "int", "required": True},
        "frequency":       {"prompt": "When should you take it? Say a time like 9:45 AM, or morning / afternoon / night.", "type": "str", "required": True},
        "daily_consumption": {"prompt": "How many do you take per day?", "type": "int", "required": True},
        "pharmacy_contact":  {"prompt": "Want to save your pharmacy's number for auto-refill? Say the number or 'skip'.", "type": "str", "required": False},
    },
    "EDIT_MEDICINE": {
        "medicine_name":  {"prompt": "Which medicine do you want to update?", "type": "str", "required": True},
        "field_to_edit":  {"prompt": "What do you want to change? (dosage / stock / time / daily amount)", "type": "str", "required": True},
        "new_value":      {"prompt": "What should the new value be?", "type": "str", "required": True},
    },
    "DELETE_MEDICINE": {
        "medicine_name": {"prompt": "Which medicine do you want to remove?", "type": "str", "required": True},
    },
    "TAKE_MEDICINE": {
        "medicine_name": {"prompt": "Which medicine did you take?", "type": "str", "required": True},
    },
    "ADD_REMINDER": {
        "reminder_title": {"prompt": "What's the event? E.g. 'Grandson Arjun's birthday' or 'Doctor appointment'.", "type": "str", "required": True},
        "reminder_type":  {"prompt": "What type? Birthday, anniversary, appointment, religious event, or other?", "type": "str", "required": True},
        "reminder_date":  {"prompt": "When is it? Say '15 March' or 'next Tuesday'.", "type": "date", "required": True},
        "auto_greeting":  {"prompt": "Should I auto-send a WhatsApp greeting on this date? Say yes or no.", "type": "bool", "required": False},
        "contact_number": {"prompt": "What's their WhatsApp number for the greeting?", "type": "str", "required": False},
    },
    "DELETE_REMINDER": {
        "reminder_title": {"prompt": "Which reminder do you want to remove?", "type": "str", "required": True},
    },
    "ADD_CONTACT": {
        "contact_name":         {"prompt": "What's their name?", "type": "str", "required": True},
        "contact_phone":        {"prompt": "What's their phone number?", "type": "str", "required": True},
        "contact_relationship": {"prompt": "Who are they? Son, daughter, doctor, pharmacy, or caregiver?", "type": "str", "required": True},
        "is_primary":           {"prompt": "Should they be your primary emergency contact? Say yes or no.", "type": "bool", "required": False},
    },
    "LOG_WELLNESS": {
        "mood":        {"prompt": "How are you feeling today? Great, good, okay, low, or bad?", "type": "str", "required": True},
        "sleep":       {"prompt": "How did you sleep? Good, fair, or poor?", "type": "str", "required": True},
        "pain_level":  {"prompt": "Any pain today? Rate 0 (no pain) to 10 (worst pain).", "type": "int", "required": True},
        "appetite":    {"prompt": "How's your appetite? Good, fair, or poor?", "type": "str", "required": True},
    },
}

INTENT_GREETINGS: dict[str, str] = {
    "ADD_MEDICINE":    "Sure, let's add a new medicine! 💊",
    "EDIT_MEDICINE":   "No problem, let's update your medicine.",
    "DELETE_MEDICINE": "Okay, let's remove that medicine.",
    "TAKE_MEDICINE":   "Let me mark that as taken! ✓",
    "ADD_REMINDER":    "Let's set up a reminder! 📅",
    "DELETE_REMINDER": "Okay, I'll remove that reminder.",
    "ADD_CONTACT":     "Let's add a new emergency contact! 👤",
    "LOG_WELLNESS":    "Let's do your wellness check-in! 🧘",
}


# ── Session dataclass ──────────────────────────────────────────────────────

@dataclass
class AgentSession:
    user_id: str
    active_intent: Optional[str] = None
    collected_slots: dict[str, Any] = field(default_factory=dict)
    pending_confirmation: bool = False

    def get_next_empty_slot(self) -> Optional[tuple[str, dict]]:
        if not self.active_intent or self.active_intent not in REQUIRED_SLOTS:
            return None
        for slot_name, cfg in REQUIRED_SLOTS[self.active_intent].items():
            if slot_name not in self.collected_slots:
                return (slot_name, cfg)
        return None

    def all_required_filled(self) -> bool:
        if not self.active_intent:
            return False
        for slot_name, cfg in REQUIRED_SLOTS[self.active_intent].items():
            if cfg["required"] and slot_name not in self.collected_slots:
                return False
        return True

    def confirmation_message(self) -> str:
        s = self.collected_slots
        if self.active_intent == "ADD_MEDICINE":
            return (
                f"Let me confirm:\n"
                f"💊 Medicine: {s.get('medicine_name', '?')}\n"
                f"💊 Dosage: {s.get('dosage', '?')}\n"
                f"📦 Stock: {s.get('stock_count', '?')} tablets\n"
                f"⏰ Time: {s.get('frequency', '?')}\n"
                f"📊 Daily: {s.get('daily_consumption', '?')} per day\n\n"
                f"Should I add this? Say yes to confirm."
            )
        if self.active_intent == "DELETE_MEDICINE":
            return (
                f"You want to remove **{s.get('medicine_name', '?')}** from your medicines. "
                f"This will stop all reminders for it. Are you sure? Say yes to confirm."
            )
        if self.active_intent == "TAKE_MEDICINE":
            return f"Marking **{s.get('medicine_name', '?')}** as taken now. Confirm?"
        if self.active_intent == "ADD_REMINDER":
            msg = (
                f"Let me confirm:\n"
                f"📅 Event: {s.get('reminder_title', '?')}\n"
                f"📋 Type: {s.get('reminder_type', '?')}\n"
                f"🗓️ Date: {s.get('reminder_date', '?')}"
            )
            if s.get("auto_greeting"):
                msg += f"\n📱 Auto-greeting: Yes (to {s.get('contact_number', 'N/A')})"
            return msg + "\n\nShould I save this? Say yes to confirm."
        if self.active_intent == "ADD_CONTACT":
            return (
                f"Let me confirm:\n"
                f"👤 Name: {s.get('contact_name', '?')}\n"
                f"📱 Phone: {s.get('contact_phone', '?')}\n"
                f"👨‍👩‍👦 Relationship: {s.get('contact_relationship', '?')}\n"
                f"⭐ Primary: {'Yes' if s.get('is_primary') else 'No'}\n\n"
                f"Should I save this? Say yes to confirm."
            )
        if self.active_intent == "LOG_WELLNESS":
            return (
                f"Here's your check-in:\n"
                f"😊 Mood: {s.get('mood', '?')}\n"
                f"😴 Sleep: {s.get('sleep', '?')}\n"
                f"🤕 Pain: {s.get('pain_level', '?')}/10\n"
                f"🍽️ Appetite: {s.get('appetite', '?')}\n\n"
                f"Should I log this? Say yes to confirm."
            )
        if self.active_intent == "DELETE_REMINDER":
            return f"Remove reminder for **{s.get('reminder_title', '?')}**? Say yes to confirm."
        return "Please confirm — say yes or no."

    def reset(self) -> None:
        self.active_intent = None
        self.collected_slots = {}
        self.pending_confirmation = False
