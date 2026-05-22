"""
Shared LLM client — wraps the Groq OpenAI-compatible endpoint.
Imported by routers/chat.py and agent/orchestrator.py.
"""
from __future__ import annotations

import httpx

from config import settings

_FALLBACK = (
    "I'm having trouble connecting right now. "
    "Please try again in a moment, or call a family member if you need help. 💙"
)


async def call_llm(
    messages: list[dict],
    *,
    temperature: float = 0.7,
    max_tokens: int = 300,
) -> str:
    """POST to Groq and return the assistant reply."""
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.llm_base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        print(f"[LLM ERROR] {exc}")
        return _FALLBACK
