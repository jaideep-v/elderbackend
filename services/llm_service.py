"""
High-level LLM helpers — thin wrappers around call_llm for specific use cases.
"""
from __future__ import annotations

import json

from services.llm_client import call_llm

_SYSTEM_PROMPT_EN = """\
You are ElderWise AI, a warm, caring, and patient companion for elderly users.
Keep responses short (2-4 sentences), clear, and friendly.
Never use jargon. Always be encouraging and positive.
If the user mentions pain, distress, or an emergency, gently suggest calling a family member or doctor.
"""

_SYSTEM_PROMPT_TA = """\
நீங்கள் ElderWise AI, ஒரு அன்பான மற்றும் பொறுமையான துணை.
பதில்களை சுருக்கமாகவும் (2-4 வாக்கியங்கள்) தெளிவாகவும் இருக்கட்டும்.
"""


async def chat(user_id: str, message: str, language: str = "en") -> str:
    system = _SYSTEM_PROMPT_TA if language == "ta" else _SYSTEM_PROMPT_EN
    return await call_llm(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ],
        temperature=0.7,
        max_tokens=256,
    )


async def analyze_sentiment(text: str) -> tuple[float, bool]:
    """Returns (sentiment_score 1-5, alert_triggered). Falls back to (3.0, False) on error."""
    prompt = f"""\
Analyze this elderly patient's wellness check-in and respond with ONLY valid JSON.

Check-in data: {text}

Respond with exactly this JSON and nothing else:
{{"sentiment_score": <float 1.0-5.0>, "alert_triggered": <true|false>}}

Rules:
- sentiment_score: 1=very negative, 3=neutral, 5=very positive
- alert_triggered: true only if there are strong signs of distress, severe pain (4-5), very low mood (1), or emergency
"""
    try:
        raw = await call_llm(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=64,
        )
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)
        score = float(parsed.get("sentiment_score", 3.0))
        alert = bool(parsed.get("alert_triggered", False))
        return max(1.0, min(5.0, score)), alert
    except Exception:
        return 3.0, False
