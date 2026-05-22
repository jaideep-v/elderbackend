# ElderWise AI — Backend

FastAPI backend for the ElderWise AI Flutter app.

## Stack
| Layer | Tech |
|-------|------|
| API | FastAPI + Uvicorn |
| LLM | LM Studio (Mistral 7B, OpenAI-compatible) |
| Database | Supabase (Postgres) |
| News | RSS feeds via feedparser |
| WhatsApp | Twilio |
| OCR | pytesseract |

## Quick Start

```bash
cd elderwise_backend

# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and fill in env vars
cp .env.example .env

# 4. Run Supabase schema (once)
#    Paste supabase_schema.sql into Supabase Dashboard → SQL editor

# 5. Start LM Studio with Mistral 7B on port 1234

# 6. Start the backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000/docs** for interactive API docs.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat` | AI companion chat (Mistral 7B) |
| `GET`  | `/api/news/digest` | News articles from RSS (`?category=all\|health\|local\|sports\|weather`) |
| `POST` | `/api/wellness/analyze` | Sentiment + alert analysis of check-in |
| `GET`  | `/api/wellness/trend` | Placeholder (computed in Flutter from Supabase) |
| `POST` | `/api/alert/whatsapp` | Send WhatsApp message via Twilio |
| `POST` | `/api/alert/sos` | SOS blast to all contacts |
| `POST` | `/api/medicine/ocr` | Extract medicine names from prescription image |
| `GET`  | `/health` | Health check |

## Flutter connection

The Android emulator maps `10.0.2.2` to your machine's localhost.
All URLs in `lib/utils/constants.dart` already point to `http://10.0.2.2:8000`.

For a physical device on the same Wi-Fi, update `backendBase` to your machine's LAN IP (e.g. `http://192.168.1.x:8000`).

## Environment Variables

See `.env.example` for all variables.

- **LLM** — point `LLM_BASE_URL` at LM Studio (`http://localhost:1234/v1`) or any OpenAI-compatible server.
- **Twilio** — optional; if not set, WhatsApp messages are printed to console (dev mode).
- **Supabase** — `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` for server-side queries (future use).

## OCR Setup (pytesseract)

```bash
# Windows
choco install tesseract
# Ubuntu
sudo apt install tesseract-ocr
# macOS
brew install tesseract
```
