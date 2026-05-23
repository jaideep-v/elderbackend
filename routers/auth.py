"""
User auth — register & login.
Passwords are hashed with bcrypt via passlib.
Returns user_id + profile on success (no JWT for simplicity — user_id is the session token).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.supabase_service import get_supabase_client

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── lazy import passlib so startup never fails even if optional ────
try:
    from passlib.context import CryptContext
    _pwd = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
    _hash   = lambda p: _pwd.hash(p)
    _verify = lambda p, h: _pwd.verify(p, h)
except ImportError:
    import hashlib
    _SECRET = b"elderwise-fallback"
    _hash   = lambda p: hashlib.sha256(_SECRET + p.encode()).hexdigest()
    _verify = lambda p, h: _hash(p) == h


class RegisterIn(BaseModel):
    name: str
    email: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


def _user_out(row: dict) -> dict:
    return {
        "user_id":   row["id"],
        "name":      row["name"],
        "email":     row["email"],
        "plan":      row.get("plan", "free"),
        "plan_activated_at": row.get("plan_activated_at"),
    }


@router.post("/register")
async def register(body: RegisterIn) -> dict:
    db = get_supabase_client()
    if not db:
        raise HTTPException(503, detail="Database unavailable")

    try:
        existing = db.table("users").select("id").eq("email", body.email).execute()
        if existing.data:
            raise HTTPException(409, detail="Email already registered")

        pw_hash = _hash(body.password)
        result = (
            db.table("users")
            .insert({"name": body.name, "email": body.email, "password_hash": pw_hash})
            .execute()
        )
        if not result.data:
            raise HTTPException(500, detail="Failed to create account")

        return _user_out(result.data[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"Registration error: {str(e)}")


@router.post("/login")
async def login(body: LoginIn) -> dict:
    db = get_supabase_client()
    if not db:
        raise HTTPException(503, detail="Database unavailable")

    try:
        result = db.table("users").select("*").eq("email", body.email).execute()
        if not result.data:
            raise HTTPException(401, detail="Invalid email or password")

        user = result.data[0]
        if not _verify(body.password, user["password_hash"]):
            raise HTTPException(401, detail="Invalid email or password")

        return _user_out(user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"Login error: {str(e)}")


@router.get("/profile")
async def get_profile(user_id: str) -> dict:
    db = get_supabase_client()
    if not db:
        raise HTTPException(503, detail="Database unavailable")

    try:
        result = db.table("users").select("*").eq("id", user_id).execute()
        if not result.data:
            raise HTTPException(404, detail="User not found")

        return _user_out(result.data[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"Profile error: {str(e)}")
