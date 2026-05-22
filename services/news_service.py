"""
Fetches news articles from free RSS feeds, grouped by category.
Returns a normalised list ready for the Flutter NewsCard widget.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx

from config import settings

# ── RSS sources by category ─────────────────────────────────────

_FEEDS: dict[str, list[str]] = {
    "health": [
        "https://feeds.feedburner.com/ndtvnews-health",
        "https://rss.medicalnewstoday.com/featurednews.xml",
        "https://www.who.int/rss-feeds/news-english.xml",
    ],
    "local": [
        "https://feeds.feedburner.com/ndtvnews-latest",
        "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",
    ],
    "sports": [
        "https://feeds.feedburner.com/ndtvnews-sports",
        "https://sportstar.thehindu.com/feeder/default.rss",
    ],
    "weather": [
        "https://timesofindia.indiatimes.com/rssfeeds/weather.cms",
    ],
}

# "all" merges a subset of each category
_ALL_FEEDS = [url for urls in _FEEDS.values() for url in urls[:1]]


def _clean_html(raw: str) -> str:
    return re.sub(r"<[^>]+>", "", raw or "").strip()


def _stable_id(link: str, title: str) -> str:
    return hashlib.md5(f"{link}{title}".encode()).hexdigest()[:12]


def _parse_feed_entries(feed_data: str, category: str) -> list[dict[str, Any]]:
    parsed = feedparser.parse(feed_data)
    articles = []
    for entry in parsed.entries[: settings.news_max_articles]:
        summary = _clean_html(
            entry.get("summary") or entry.get("description") or ""
        )[:300]
        title = _clean_html(entry.get("title", "Untitled"))
        link = entry.get("link", "")
        pub = entry.get("published", datetime.now(timezone.utc).isoformat())
        articles.append(
            {
                "id": _stable_id(link, title),
                "title": title,
                "summary": summary,
                "url": link,
                "category": category,
                "publishedAt": pub,
                "imageUrl": None,
            }
        )
    return articles


async def _fetch_feed(client: httpx.AsyncClient, url: str, category: str) -> list[dict]:
    try:
        resp = await client.get(url, timeout=10, follow_redirects=True)
        resp.raise_for_status()
        return _parse_feed_entries(resp.text, category)
    except Exception:
        return []


async def fetch_articles(category: str = "all") -> list[dict[str, Any]]:
    feed_urls: list[tuple[str, str]]  # (url, category_label)
    if category == "all":
        feed_urls = [(url, cat) for cat, urls in _FEEDS.items() for url in urls[:1]]
    else:
        feed_urls = [(url, category) for url in _FEEDS.get(category, _ALL_FEEDS)]

    async with httpx.AsyncClient(headers={"User-Agent": "ElderWiseBot/1.0"}) as client:
        tasks = [_fetch_feed(client, url, cat) for url, cat in feed_urls]
        results = await asyncio.gather(*tasks)

    articles: list[dict] = []
    seen: set[str] = set()
    for batch in results:
        for a in batch:
            if a["id"] not in seen:
                seen.add(a["id"])
                articles.append(a)

    # Sort newest first (best-effort)
    articles.sort(key=lambda a: a["publishedAt"], reverse=True)
    return articles[: settings.news_max_articles]
