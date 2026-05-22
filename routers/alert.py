from fastapi import APIRouter
from pydantic import BaseModel

from services.alert_service import send_whatsapp, blast_sos
from services.supabase_service import get_emergency_contacts

router = APIRouter(prefix="/api/alert", tags=["alerts"])


class WhatsAppRequest(BaseModel):
    phone: str
    message: str


class SosRequest(BaseModel):
    user_id: str
    location: dict          # {"lat": float, "lng": float}
    contacts: list[str] = []   # optional — overrides Supabase lookup
    user_name: str = "the user"


@router.post("/whatsapp")
async def whatsapp_alert(body: WhatsAppRequest) -> dict:
    ok = send_whatsapp(phone=body.phone, message=body.message)
    return {"sent": ok}


@router.post("/sos")
async def sos_blast(body: SosRequest) -> dict:
    lat = body.location.get("lat", 0.0)
    lng = body.location.get("lng", 0.0)
    location_url = f"https://maps.google.com/?q={lat},{lng}"

    # Use contacts from request body; fall back to Supabase lookup by user_id
    contact_numbers = list(body.contacts)
    if not contact_numbers:
        db_contacts = await get_emergency_contacts(body.user_id)
        contact_numbers = [c["phone"] for c in db_contacts if c.get("phone")]

    if not contact_numbers:
        # Dev/demo mode — nothing to send, log and return
        print(f"[SOS] No contacts found for user '{body.user_id}'. Location: {location_url}")
        return {"contacts_alerted": 0, "location_url": location_url}

    results = blast_sos(
        contacts=contact_numbers,
        location_url=location_url,
        user_name=body.user_name,
    )
    return {
        "contacts_alerted": sum(1 for r in results if r),
        "location_url": location_url,
    }
