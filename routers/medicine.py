import io
import re

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image

router = APIRouter(prefix="/api/medicine", tags=["medicine"])


def _extract_with_tesseract(image: Image.Image) -> list[str]:
    try:
        import pytesseract  # type: ignore
        text = pytesseract.image_to_string(image, lang="eng")
        return _parse_medicine_names(text)
    except Exception:
        return []


def _parse_medicine_names(text: str) -> list[str]:
    """
    Heuristic: lines that look like medicine names — capitalised words,
    often followed by dosage (mg / ml / tablet).
    """
    pattern = re.compile(
        r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s*"
        r"(?:\d+\s*(?:mg|ml|mcg|IU|tablet|cap|tabs))?",
        re.IGNORECASE,
    )
    candidates: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = pattern.search(line)
        if match:
            name = match.group(1).strip()
            if 2 < len(name) < 60 and name not in candidates:
                candidates.append(name)
    return candidates[:10]  # cap at 10 medicines per image


@router.post("/ocr")
async def medicine_ocr(image: UploadFile = File(...)) -> dict:
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Upload must be an image file.")

    raw = await image.read()
    try:
        pil_image = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not decode image.")

    # Upscale small images for better OCR accuracy
    w, h = pil_image.size
    if w < 800:
        scale = 800 / w
        pil_image = pil_image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    medicines = _extract_with_tesseract(pil_image)

    return {"medicines": medicines, "count": len(medicines)}
