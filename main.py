"""
ElderWise AI — FastAPI Backend
Run: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import chat, news, wellness, alert, medicine, reminder, voice

app = FastAPI(
    title="ElderWise AI API",
    description="Backend for the ElderWise AI Flutter app — voice-first elderly companion",
    version="1.0.0",
)

# ── CORS (allow Flutter on Android emulator / local network) ─────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────
app.include_router(chat.router)
app.include_router(news.router)
app.include_router(wellness.router)
app.include_router(alert.router)
app.include_router(medicine.router)
app.include_router(reminder.router)
app.include_router(voice.router)


# ── Health check ─────────────────────────────────────────────────
@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "service": "ElderWise AI API"}


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "service": "ElderWise AI API",
        "docs": "/docs",
        "endpoints": [
            "POST /api/chat",
            "GET  /api/news/digest",
            "POST /api/wellness/analyze",
            "GET  /api/wellness/trend",
            "POST /api/alert/whatsapp",
            "POST /api/alert/sos",
            "POST /api/medicine/ocr",
            "POST /api/reminder/greet",
            "POST /api/chat/voice",
        ],
    }
