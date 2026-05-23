"""
Chat router — three endpoints:
  POST /api/chat         — simple chat (backwards-compatible)
  POST /api/chat/context — context-aware chat with Supabase data + history
  POST /api/chat/agent   — agentic chat: intent detection + CRUD actions
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agent.orchestrator import process_agent_message
from services.context_builder import build_user_context
from services.llm_client import call_llm
from services.prompts import get_contextual_prompt

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ── Request / Response models ─────────────────────────────────────

class ChatRequest(BaseModel):
    user_id: str
    message: str
    language: str = "en"


class ContextChatRequest(BaseModel):
    user_id: str
    message: str
    language: str = "en"
    chat_history: list[dict[str, str]] = Field(
        default_factory=list,
        description='[{"role":"user","content":"..."},{"role":"assistant","content":"..."}]',
    )


class ChatResponse(BaseModel):
    response: str
    context_loaded: bool = False


# ── LLM helper ────────────────────────────────────────────────────

_FALLBACK = (
    "I'm having trouble connecting right now. "
    "Please try again in a moment, or call a family member if you need help. 💙"
)


async def _call_llm(messages: list[dict[str, str]]) -> str:
    return await call_llm(messages)


# ── Simple chat (backwards-compatible) ───────────────────────────

_SIMPLE_SYSTEM_EN = (
    "You are ElderWise AI, a warm, caring, and patient companion for elderly users. "
    "Keep responses short (2-4 sentences), clear, and friendly. Never use jargon. "
    "Always be encouraging. If the user mentions pain or emergency, suggest calling family or doctor."
)
_SIMPLE_SYSTEM_TA = (
    "நீங்கள் ElderWise AI, ஒரு அன்பான மற்றும் பொறுமையான துணை. "
    "பதில்களை சுருக்கமாகவும் (2-4 வாக்கியங்கள்) தெளிவாகவும் இருக்கட்டும்."
)


@router.post("", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest) -> ChatResponse:
    system = _SIMPLE_SYSTEM_TA if body.language == "ta" else _SIMPLE_SYSTEM_EN
    reply = await _call_llm([
        {"role": "system", "content": system},
        {"role": "user", "content": body.message},
    ])
    return ChatResponse(response=reply, context_loaded=False)


# ── Context-aware chat ────────────────────────────────────────────

@router.post("/context", response_model=ChatResponse)
async def contextual_chat(body: ContextChatRequest) -> ChatResponse:
    # 1. Fetch user context from Supabase (cached 5 min)
    user_context = await build_user_context(body.user_id)
    context_loaded = bool(user_context)

    # 2. Build system prompt
    system_prompt = get_contextual_prompt(user_context, language=body.language)

    # 3. Assemble messages: system + last 10 history turns + new message
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for turn in body.chat_history[-10:]:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": body.message})

    # 4. Call Mistral
    reply = await _call_llm(messages)
    return ChatResponse(response=reply, context_loaded=context_loaded)


# ── Agent chat (intent + CRUD) ─────────────────────────────────────

class AgentChatRequest(BaseModel):
    user_id: str
    message: str
    language: str = "en"
    chat_history: list[dict[str, str]] = Field(default_factory=list)


class AgentChatResponse(BaseModel):
    response: str
    action_taken: bool = False
    active_intent: str | None = None


@router.post("/agent", response_model=AgentChatResponse)
async def agent_chat(body: AgentChatRequest) -> AgentChatResponse:
    result = await process_agent_message(
        user_id=body.user_id,
        message=body.message,
        chat_history=body.chat_history,
        language=body.language,
    )
    return AgentChatResponse(
        response=result["response"],
        action_taken=result.get("action_taken", False),
        active_intent=result.get("active_intent"),
    )
