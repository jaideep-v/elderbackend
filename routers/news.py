from typing import Any

from fastapi import APIRouter, Query

from services.news_service import fetch_articles

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("/digest")
async def news_digest(
    category: str = Query(default="all", description="all | health | local | sports | weather"),
) -> dict[str, Any]:
    articles = await fetch_articles(category=category)
    return {"articles": articles, "count": len(articles)}
