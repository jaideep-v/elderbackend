from __future__ import annotations

import json
import re

from services.llm_client import call_llm

_PROMPT = """\
You are an intent classifier for an elderly care app. Detect the intent and extract entities.

Available intents:
ADD_MEDICINE, EDIT_MEDICINE, DELETE_MEDICINE, TAKE_MEDICINE,
ADD_REMINDER, EDIT_REMINDER, DELETE_REMINDER,
ADD_CONTACT, EDIT_CONTACT, DELETE_CONTACT,
LOG_WELLNESS, CHECK_MEDICINE, CHECK_REMINDER, CHECK_WELLNESS,
FETCH_NEWS, GENERAL_CHAT, TRIGGER_SOS, CALL_CONTACT

Examples:
"add medicine" → ADD_MEDICINE
"add aspirin 500mg" → ADD_MEDICINE
"I took my metformin" → TAKE_MEDICINE
"took aspirin just now" → TAKE_MEDICINE
"log wellness" → LOG_WELLNESS
"wellness check in" → LOG_WELLNESS
"how am I feeling" → LOG_WELLNESS
"log my mood" → LOG_WELLNESS
"I feel good today" → LOG_WELLNESS
"add a reminder" → ADD_REMINDER
"set reminder for birthday" → ADD_REMINDER
"add emergency contact" → ADD_CONTACT
"what medicines do I take" → CHECK_MEDICINE
"delete aspirin" → DELETE_MEDICINE
"SOS help" → TRIGGER_SOS
"hello how are you" → GENERAL_CHAT
"hai" → GENERAL_CHAT
"hi" → GENERAL_CHAT
"hey" → GENERAL_CHAT
"good morning" → GENERAL_CHAT
"good evening" → GENERAL_CHAT
"thanks" → GENERAL_CHAT
"thank you" → GENERAL_CHAT
"how are you" → GENERAL_CHAT
"what can you do" → GENERAL_CHAT
"help me" → GENERAL_CHAT
"what's the news today" → FETCH_NEWS
"latest news" → FETCH_NEWS
"show me health news" → FETCH_NEWS
"any sports news" → FETCH_NEWS
"tell me today's headlines" → FETCH_NEWS
"news from India" → FETCH_NEWS

Respond ONLY with valid JSON, nothing else:
{{
  "intent": "INTENT_NAME",
  "confidence": 0.0,
  "entities": {{
    "medicine_name": null,
    "dosage": null,
    "stock_count": null,
    "frequency": null,
    "daily_consumption": null,
    "reminder_title": null,
    "reminder_date": null,
    "reminder_type": null,
    "contact_name": null,
    "contact_phone": null,
    "contact_relationship": null,
    "mood": null,
    "sleep": null,
    "pain_level": null,
    "appetite": null,
    "news_category": null
  }}
}}

User message: "{message}"
Recent context: "{context}"
"""


async def detect_intent(message: str, context: str) -> dict:
    """Returns {intent, confidence, entities} dict."""
    prompt = _PROMPT.format(message=message, context=context)
    raw = await call_llm(
        [
            {"role": "system", "content": "You are a JSON-only intent classifier. Output only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=500,
    )

    # Extract JSON block from the response
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return {"intent": "GENERAL_CHAT", "confidence": 0.0, "entities": {}}
