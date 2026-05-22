"""
Voice chat router — POST /api/chat/voice
Returns text response + edge-tts audio as base64 MP3.
Reuses the existing agent orchestrator for intent detection + CRUD.
"""
from __future__ import annotations

import base64
import io
import re

import edge_tts
from fastapi import APIRouter
from pydantic import BaseModel, Field

from agent.orchestrator import process_agent_message

router = APIRouter(prefix="/api/chat", tags=["voice"])


# ── Request / Response ────────────────────────────────────────────

class VoiceChatRequest(BaseModel):
    user_id: str
    message: str
    language: str = "en"
    chat_history: list[dict[str, str]] = Field(default_factory=list)


class VoiceChatResponse(BaseModel):
    response: str
    audio_base64: str = ""
    action_taken: bool = False
    active_intent: str | None = None


# ── Voice map ─────────────────────────────────────────────────────

_VOICE_MAP = {
    "en": "en-IN-NeerjaNeural",
    "ta": "ta-IN-PallaviNeural",
}


# ── Emoji / formatting cleaner ────────────────────────────────────

_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U00002600-\U000026FF"
    "\U00002700-\U000027BF"
    "]+",
    flags=re.UNICODE,
)


def _clean_for_speech(text: str) -> str:
    """Strip emoji, markdown, and bullet markers that TTS can't handle."""
    text = _EMOJI_RE.sub("", text)
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"_+", " ", text)
    text = re.sub(r"[•●▪]", "", text)
    text = re.sub(r"^\s*[-]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


# ── Audio generation ──────────────────────────────────────────────

async def _generate_audio(text: str, language: str = "en") -> bytes:
    """Generate MP3 audio bytes using edge-tts."""
    voice = _VOICE_MAP.get(language, "en-IN-NeerjaNeural")
    communicate = edge_tts.Communicate(text, voice, rate="-10%", pitch="+0Hz")
    buffer = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buffer.write(chunk["data"])
    return buffer.getvalue()


# ── Endpoint ──────────────────────────────────────────────────────

@router.post("/voice", response_model=VoiceChatResponse)
async def voice_chat(body: VoiceChatRequest) -> VoiceChatResponse:
    # 1. Get text response from agent orchestrator (with voice_mode)
    result = await process_agent_message(
        user_id=body.user_id,
        message=body.message,
        chat_history=body.chat_history,
        voice_mode=True,
    )
    response_text = result["response"]

    # 2. Clean text for TTS and generate audio
    speech_text = _clean_for_speech(response_text)
    audio_b64 = ""
    if speech_text:
        try:
            audio_bytes = await _generate_audio(speech_text, body.language)
            audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        except Exception as exc:
            print(f"[edge-tts ERROR] {exc}")

    return VoiceChatResponse(
        response=response_text,
        audio_base64=audio_b64,
        action_taken=result.get("action_taken", False),
        active_intent=result.get("active_intent"),
    )
