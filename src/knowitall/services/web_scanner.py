"""Web scanner service for multi-source intelligence gathering.

Scans Reddit, Hacker News, Product Hunt, review sites, trend tools,
and other sources for startup-relevant signals.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

import feedparser
import httpx

from knowitall.config import AppConfig, get_config
from knowitall.models.scout_report import (
    ComplaintSource,
    TechTrend,
    TrendSource,
    UserComplaint,
)

logger = logging.getLogger(__name__)


def _hash_id(prefix: str, text: str) -> str:
    return f"{prefix}-{hashlib.sha256(text.encode()).hexdigest()[:10]}"


# ---------------------------------------------------------------------------
# Reddit scanning
# ---------------------------------------------------------------------------

_REDDIT_SUBREDDITS = [
    "Entrepreneur",
    "startups",
    "smallbusiness",
    "SaaS",
    "artificial",
]


async def scan_reddit(
    client: httpx.AsyncClient,
    subreddits: list[str] | None = None,
    limit: int = 25,
) -> list[UserComplaint]:
    """Fetch recent posts from startup-related subreddits for complaints."""
    subs = subreddits or _REDDIT_SUBREDDITS
    complaints: list[UserComplaint] = []

    for sub in subs:
        url = f"https://old.reddit.com/r/{sub}/hot.json"
        try:
            resp = await client.get(
                url,
                params={"limit": str(limit)},
                headers={"User-Agent": "knowItAll/0.1"},
                follow_redirects=True,
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            logger.warning("Failed to fetch Reddit r/%s", sub)
            continue

        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            title = post.get("title", "")
            selftext = post.get("selftext", "")
            permalink = post.get("permalink", "")
            if not title:
                continue

            # Look for complaint-like posts
            lower = f"{title} {selftext}".lower()
            pain_cues = [
                "frustrated",
                "hate",
                "broken",
                "need",
                "wish",
                "problem",
                "pain point",
                "complaint",
                "sucks",
                "terrible",
                "missing",
                "why is there no",
                "looking for",
            ]
            hits = sum(1 for cue in pain_cues if cue in lower)
            if hits == 0:
                continue

            severity = min(hits / 4.0, 1.0)
            complaints.append(
                UserComplaint(
                    id=_hash_id("reddit", title),
                    summary=title[:200],
                    detail=selftext[:500],
                    source=ComplaintSource.REDDIT,
                    source_url=f"https://www.reddit.com{permalink}" if permalink else "",
                    quote=title[:200],
                    severity=round(severity, 2),
                    detected_at=datetime.now(timezone.utc),
                )
            )

    return complaints


# ---------------------------------------------------------------------------
# Hacker News scanning
# ---------------------------------------------------------------------------

_HN_API = "https://hacker-news.firebaseio.com/v0"


async def scan_hacker_news(
    client: httpx.AsyncClient,
    max_stories: int = 30,
) -> tuple[list[TechTrend], list[UserComplaint]]:
    """Fetch top Hacker News stories for trends and complaints."""
    trends: list[TechTrend] = []
    complaints: list[UserComplaint] = []

    try:
        resp = await client.get(f"{_HN_API}/topstories.json", timeout=15.0)
        resp.raise_for_status()
        story_ids = resp.json()[:max_stories]
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to fetch Hacker News top stories")
        return trends, complaints

    for sid in story_ids:
        try:
            resp = await client.get(f"{_HN_API}/item/{sid}.json", timeout=10.0)
            resp.raise_for_status()
            story = resp.json()
        except (httpx.HTTPError, ValueError):
            continue

        if not isinstance(story, dict):
            continue

        title = story.get("title", "")
        url = story.get("url", "")
        score = story.get("score", 0)
        if not title:
            continue

        hn_url = f"https://news.ycombinator.com/item?id={sid}"
        lower = title.lower()

        # Trend detection keywords
        trend_kws = [
            "ai",
            "llm",
            "gpt",
            "blockchain",
            "web3",
            "saas",
            "startup",
            "open source",
            "api",
            "framework",
            "launch",
            "release",
            "new",
        ]
        trend_hits = sum(1 for kw in trend_kws if kw in lower)
        if trend_hits >= 1 and score >= 50:
            trends.append(
                TechTrend(
                    id=_hash_id("hn-trend", title),
                    title=title[:200],
                    description=f"Trending on HN with {score} points.",
                    evidence=f"HN score: {score}",
                    sources=[TrendSource.HACKER_NEWS],
                    source_urls=[hn_url],
                    interest_score=round(min(score / 500.0, 1.0), 2),
                )
            )

        # Complaint detection
        complaint_kws = [
            "broken",
            "hate",
            "frustrated",
            "problem",
            "sucks",
            "terrible",
            "why",
            "missing",
        ]
        complaint_hits = sum(1 for kw in complaint_kws if kw in lower)
        if complaint_hits >= 1:
            complaints.append(
                UserComplaint(
                    id=_hash_id("hn-complaint", title),
                    summary=title[:200],
                    source=ComplaintSource.HACKER_NEWS,
                    source_url=hn_url,
                    quote=title[:200],
                    severity=round(min(complaint_hits / 3.0, 1.0), 2),
                    detected_at=datetime.now(timezone.utc),
                )
            )

    return trends, complaints


# ---------------------------------------------------------------------------
# Product Hunt scanning
# ---------------------------------------------------------------------------


async def scan_product_hunt(
    client: httpx.AsyncClient,
) -> list[TechTrend]:
    """Fetch today's top Product Hunt launches for trend detection."""
    trends: list[TechTrend] = []
    try:
        resp = await client.get(
            "https://www.producthunt.com/feed",
            headers={"User-Agent": "knowItAll/0.1"},
            follow_redirects=True,
            timeout=15.0,
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:10]:
            title = entry.get("title", "").strip()
            if not title:
                continue
            link = entry.get("link", "https://www.producthunt.com")
            trends.append(
                TechTrend(
                    id=_hash_id("ph-trend", title),
                    title=title,
                    description="Trending on Product Hunt today.",
                    evidence="Featured on Product Hunt front page.",
                    sources=[TrendSource.PRODUCT_HUNT],
                    source_urls=[link],
                    interest_score=0.6,
                )
            )
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to scan Product Hunt")

    return trends


# ---------------------------------------------------------------------------
# Combined scanner
# ---------------------------------------------------------------------------


async def scan_all_sources(
    client: httpx.AsyncClient,
    config: AppConfig | None = None,
) -> tuple[list[TechTrend], list[UserComplaint]]:
    """Run all scanners and merge results."""
    all_trends: list[TechTrend] = []
    all_complaints: list[UserComplaint] = []

    # Reddit
    reddit_complaints = await scan_reddit(client)
    all_complaints.extend(reddit_complaints)

    # Hacker News
    hn_trends, hn_complaints = await scan_hacker_news(client)
    all_trends.extend(hn_trends)
    all_complaints.extend(hn_complaints)

    # Product Hunt
    ph_trends = await scan_product_hunt(client)
    all_trends.extend(ph_trends)

    # Deduplicate by id
    seen_trend_ids: set[str] = set()
    unique_trends: list[TechTrend] = []
    for t in all_trends:
        if t.id not in seen_trend_ids:
            seen_trend_ids.add(t.id)
            unique_trends.append(t)

    seen_complaint_ids: set[str] = set()
    unique_complaints: list[UserComplaint] = []
    for c in all_complaints:
        if c.id not in seen_complaint_ids:
            seen_complaint_ids.add(c.id)
            unique_complaints.append(c)

    return unique_trends, unique_complaints
