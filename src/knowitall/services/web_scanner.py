"""Web scanner service for multi-source intelligence gathering.

Scans Reddit, Hacker News, Product Hunt, review sites, trend tools,
and other sources for startup-relevant signals.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
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
# Google Trends scanning
# ---------------------------------------------------------------------------

_GOOGLE_TRENDS_RSS = "https://trends.google.com/trending/rss?geo=US"


async def scan_google_trends(
    client: httpx.AsyncClient,
) -> list[TechTrend]:
    """Fetch Google Trends RSS feed for trending topics."""
    trends: list[TechTrend] = []
    try:
        resp = await client.get(
            _GOOGLE_TRENDS_RSS,
            headers={"User-Agent": "knowItAll/0.1"},
            follow_redirects=True,
            timeout=15.0,
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:15]:
            title = entry.get("title", "").strip()
            if not title:
                continue
            link = entry.get("link", "https://trends.google.com")
            description = entry.get("summary", "").strip()[:300]
            trends.append(
                TechTrend(
                    id=_hash_id("gtrends", title),
                    title=title[:200],
                    description=description or "Trending on Google Trends.",
                    evidence="Featured in Google Trends RSS feed.",
                    sources=[TrendSource.GOOGLE_TRENDS],
                    source_urls=[link],
                    interest_score=0.7,
                )
            )
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to scan Google Trends")

    return trends


# ---------------------------------------------------------------------------
# TechCrunch scanning
# ---------------------------------------------------------------------------

_TECHCRUNCH_RSS = "https://techcrunch.com/feed/"


async def scan_techcrunch(
    client: httpx.AsyncClient,
) -> list[TechTrend]:
    """Fetch TechCrunch RSS feed for tech trends."""
    trends: list[TechTrend] = []
    try:
        resp = await client.get(
            _TECHCRUNCH_RSS,
            headers={"User-Agent": "knowItAll/0.1"},
            follow_redirects=True,
            timeout=15.0,
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:15]:
            title = entry.get("title", "").strip()
            if not title:
                continue
            link = entry.get("link", "https://techcrunch.com")
            summary = entry.get("summary", "").strip()[:300]
            trends.append(
                TechTrend(
                    id=_hash_id("tc-trend", title),
                    title=title[:200],
                    description=summary or "Featured on TechCrunch.",
                    evidence="Published on TechCrunch.",
                    sources=[TrendSource.TECHCRUNCH],
                    source_urls=[link],
                    interest_score=0.65,
                )
            )
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to scan TechCrunch")

    return trends


# ---------------------------------------------------------------------------
# Exploding Topics scanning
# ---------------------------------------------------------------------------

_EXPLODING_TOPICS_URL = "https://explodingtopics.com/blog/trending-topics"


async def scan_exploding_topics(
    client: httpx.AsyncClient,
) -> list[TechTrend]:
    """Fetch Exploding Topics page and parse for trending topic titles."""
    trends: list[TechTrend] = []
    try:
        resp = await client.get(
            _EXPLODING_TOPICS_URL,
            headers={"User-Agent": "knowItAll/0.1"},
            follow_redirects=True,
            timeout=15.0,
        )
        resp.raise_for_status()
        html = resp.text

        # Extract headings (h2/h3) as trending topics
        headings = re.findall(r"<h[23][^>]*>(.*?)</h[23]>", html, re.IGNORECASE | re.DOTALL)
        for raw_title in headings[:20]:
            title = re.sub(r"<[^>]+>", "", raw_title).strip()
            if not title or len(title) < 3:
                continue
            trends.append(
                TechTrend(
                    id=_hash_id("et-trend", title),
                    title=title[:200],
                    description="Trending on Exploding Topics.",
                    evidence="Found on Exploding Topics trending page.",
                    sources=[TrendSource.EXPLODING_TOPICS],
                    source_urls=[_EXPLODING_TOPICS_URL],
                    interest_score=0.7,
                )
            )
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to scan Exploding Topics")

    return trends


# ---------------------------------------------------------------------------
# Trustpilot scanning
# ---------------------------------------------------------------------------

_TRUSTPILOT_URL = "https://www.trustpilot.com/categories/technology_services"


async def scan_trustpilot(
    client: httpx.AsyncClient,
) -> list[UserComplaint]:
    """Fetch Trustpilot technology category page for complaint-like reviews."""
    complaints: list[UserComplaint] = []
    try:
        resp = await client.get(
            _TRUSTPILOT_URL,
            headers={"User-Agent": "knowItAll/0.1"},
            follow_redirects=True,
            timeout=15.0,
        )
        resp.raise_for_status()
        html = resp.text

        # Look for review text snippets in the page
        review_blocks = re.findall(
            r"<p[^>]*>(.*?)</p>", html, re.IGNORECASE | re.DOTALL,
        )
        pain_cues = [
            "terrible", "worst", "scam", "fraud", "awful", "horrible",
            "broken", "waste", "never", "disappointed", "poor",
        ]
        for block in review_blocks[:50]:
            text = re.sub(r"<[^>]+>", "", block).strip()
            if len(text) < 20:
                continue
            lower = text.lower()
            hits = sum(1 for cue in pain_cues if cue in lower)
            if hits == 0:
                continue
            severity = min(hits / 3.0, 1.0)
            complaints.append(
                UserComplaint(
                    id=_hash_id("tp-complaint", text),
                    summary=text[:200],
                    detail=text[:500],
                    source=ComplaintSource.TRUSTPILOT,
                    source_url=_TRUSTPILOT_URL,
                    quote=text[:200],
                    severity=round(severity, 2),
                    detected_at=datetime.now(timezone.utc),
                )
            )
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to scan Trustpilot")

    return complaints


# ---------------------------------------------------------------------------
# Consumer Affairs scanning
# ---------------------------------------------------------------------------

_CONSUMER_AFFAIRS_URL = "https://www.consumeraffairs.com/computers/"


async def scan_consumer_affairs(
    client: httpx.AsyncClient,
) -> list[UserComplaint]:
    """Fetch ConsumerAffairs technology page for complaint entries."""
    complaints: list[UserComplaint] = []
    try:
        resp = await client.get(
            _CONSUMER_AFFAIRS_URL,
            headers={"User-Agent": "knowItAll/0.1"},
            follow_redirects=True,
            timeout=15.0,
        )
        resp.raise_for_status()
        html = resp.text

        review_blocks = re.findall(
            r"<p[^>]*>(.*?)</p>", html, re.IGNORECASE | re.DOTALL,
        )
        pain_cues = [
            "terrible", "worst", "broken", "waste", "scam", "awful",
            "horrible", "poor", "disappointed", "problem", "frustrated",
        ]
        for block in review_blocks[:50]:
            text = re.sub(r"<[^>]+>", "", block).strip()
            if len(text) < 20:
                continue
            lower = text.lower()
            hits = sum(1 for cue in pain_cues if cue in lower)
            if hits == 0:
                continue
            severity = min(hits / 3.0, 1.0)
            complaints.append(
                UserComplaint(
                    id=_hash_id("ca-complaint", text),
                    summary=text[:200],
                    detail=text[:500],
                    source=ComplaintSource.CONSUMER_AFFAIRS,
                    source_url=_CONSUMER_AFFAIRS_URL,
                    quote=text[:200],
                    severity=round(severity, 2),
                    detected_at=datetime.now(timezone.utc),
                )
            )
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to scan Consumer Affairs")

    return complaints


# ---------------------------------------------------------------------------
# BBB scanning
# ---------------------------------------------------------------------------

_BBB_URL = "https://www.bbb.org/search?find_type=category&category=Computer+Software"


async def scan_bbb(
    client: httpx.AsyncClient,
) -> list[UserComplaint]:
    """Fetch BBB complaints page for software-related complaints."""
    complaints: list[UserComplaint] = []
    try:
        resp = await client.get(
            _BBB_URL,
            headers={"User-Agent": "knowItAll/0.1"},
            follow_redirects=True,
            timeout=15.0,
        )
        resp.raise_for_status()
        html = resp.text

        # Extract business/complaint titles from headings and links
        entries = re.findall(
            r"<a[^>]+href=\"([^\"]*?)\"[^>]*>(.*?)</a>",
            html,
            re.IGNORECASE | re.DOTALL,
        )
        pain_cues = [
            "complaint", "scam", "fraud", "terrible", "worst", "broken",
            "poor", "waste", "problem", "disappointed",
        ]
        for href, raw_text in entries[:50]:
            text = re.sub(r"<[^>]+>", "", raw_text).strip()
            if len(text) < 5:
                continue
            lower = text.lower()
            hits = sum(1 for cue in pain_cues if cue in lower)
            if hits == 0:
                continue
            link = href if href.startswith("http") else f"https://www.bbb.org{href}"
            severity = min(hits / 3.0, 1.0)
            complaints.append(
                UserComplaint(
                    id=_hash_id("bbb-complaint", text),
                    summary=text[:200],
                    detail=text[:500],
                    source=ComplaintSource.BBB,
                    source_url=link,
                    quote=text[:200],
                    severity=round(severity, 2),
                    detected_at=datetime.now(timezone.utc),
                )
            )
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to scan BBB")

    return complaints


# ---------------------------------------------------------------------------
# Y Combinator Requests for Startups scanning
# ---------------------------------------------------------------------------

_YC_RFS_URL = "https://www.ycombinator.com/rfs"


async def scan_yc_rfs(
    client: httpx.AsyncClient,
) -> list[TechTrend]:
    """Fetch Y Combinator Requests for Startups page for startup idea areas."""
    trends: list[TechTrend] = []
    try:
        resp = await client.get(
            _YC_RFS_URL,
            headers={"User-Agent": "knowItAll/0.1"},
            follow_redirects=True,
            timeout=15.0,
        )
        resp.raise_for_status()
        html = resp.text

        headings = re.findall(
            r"<h[123][^>]*>(.*?)</h[123]>", html, re.IGNORECASE | re.DOTALL,
        )
        for raw_title in headings[:20]:
            title = re.sub(r"<[^>]+>", "", raw_title).strip()
            if not title or len(title) < 3:
                continue
            trends.append(
                TechTrend(
                    id=_hash_id("yc-rfs", title),
                    title=title[:200],
                    description="Y Combinator Request for Startups area.",
                    evidence="Listed on YC Requests for Startups page.",
                    sources=[TrendSource.OTHER],
                    source_urls=[_YC_RFS_URL],
                    interest_score=0.8,
                )
            )
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to scan YC Requests for Startups")

    return trends


# ---------------------------------------------------------------------------
# Twitter / X scanning
# ---------------------------------------------------------------------------


async def scan_twitter(
    client: httpx.AsyncClient,
) -> list[UserComplaint]:
    """Scan Twitter/X API v2 for tech complaint tweets (requires auth)."""
    complaints: list[UserComplaint] = []
    bearer = os.environ.get("TWITTER_BEARER_TOKEN", "")
    if not bearer:
        logger.warning("TWITTER_BEARER_TOKEN not set; skipping Twitter scan")
        return complaints

    query = "(frustrated OR broken OR terrible OR hate OR sucks) (software OR app OR tech) -is:retweet lang:en"
    try:
        resp = await client.get(
            "https://api.twitter.com/2/tweets/search/recent",
            params={"query": query, "max_results": "25", "tweet_fields": "author_id,created_at,text"},
            headers={"Authorization": f"Bearer {bearer}", "User-Agent": "knowItAll/0.1"},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to fetch Twitter search results")
        return complaints

    for tweet in data.get("data", []):
        text = tweet.get("text", "")
        tweet_id = tweet.get("id", "")
        if not text:
            continue
        lower = text.lower()
        pain_cues = [
            "frustrated", "hate", "broken", "terrible", "sucks",
            "worst", "problem", "awful", "disappointed",
        ]
        hits = sum(1 for cue in pain_cues if cue in lower)
        if hits == 0:
            continue
        severity = min(hits / 3.0, 1.0)
        complaints.append(
            UserComplaint(
                id=_hash_id("twitter", text),
                summary=text[:200],
                detail=text[:500],
                source=ComplaintSource.TWITTER,
                source_url=f"https://twitter.com/i/web/status/{tweet_id}" if tweet_id else "",
                quote=text[:200],
                severity=round(severity, 2),
                detected_at=datetime.now(timezone.utc),
            )
        )

    return complaints


# ---------------------------------------------------------------------------
# LinkedIn scanning
# ---------------------------------------------------------------------------


async def scan_linkedin(
    client: httpx.AsyncClient,
) -> list[UserComplaint]:
    """Scan LinkedIn for industry pain point posts (requires auth)."""
    complaints: list[UserComplaint] = []
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
    if not token:
        logger.warning("LINKEDIN_ACCESS_TOKEN not set; skipping LinkedIn scan")
        return complaints

    try:
        resp = await client.get(
            "https://api.linkedin.com/v2/ugcPosts",
            params={"q": "authors", "count": "25"},
            headers={"Authorization": f"Bearer {token}", "User-Agent": "knowItAll/0.1"},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to fetch LinkedIn posts")
        return complaints

    for post in data.get("elements", []):
        text = post.get("commentary", post.get("text", ""))
        post_id = post.get("id", "")
        if not text:
            continue
        lower = text.lower()
        pain_cues = [
            "frustrated", "problem", "broken", "terrible", "pain point",
            "struggle", "hate", "worst", "disappointed",
        ]
        hits = sum(1 for cue in pain_cues if cue in lower)
        if hits == 0:
            continue
        severity = min(hits / 3.0, 1.0)
        complaints.append(
            UserComplaint(
                id=_hash_id("linkedin", text),
                summary=text[:200],
                detail=text[:500],
                source=ComplaintSource.LINKEDIN,
                source_url=f"https://www.linkedin.com/feed/update/urn:li:share:{post_id}" if post_id else "",
                quote=text[:200],
                severity=round(severity, 2),
                detected_at=datetime.now(timezone.utc),
            )
        )

    return complaints


# ---------------------------------------------------------------------------
# App Store Reviews scanning
# ---------------------------------------------------------------------------

_APP_STORE_IDS = [
    "333903271",   # Twitter/X
    "835599320",   # Microsoft Office
    "585027354",   # Google Authenticator
]

_APP_STORE_RSS = "https://itunes.apple.com/us/rss/customerreviews/page=1/id={app_id}/sortby=mostrecent/json"


async def scan_app_store_reviews(
    client: httpx.AsyncClient,
    app_ids: list[str] | None = None,
) -> list[UserComplaint]:
    """Fetch Apple App Store RSS reviews for popular tech apps."""
    complaints: list[UserComplaint] = []
    ids = app_ids or _APP_STORE_IDS

    pain_cues = [
        "crash", "bug", "broken", "terrible", "worst", "hate",
        "frustrated", "useless", "slow", "awful", "disappointed",
    ]

    for app_id in ids:
        url = _APP_STORE_RSS.format(app_id=app_id)
        try:
            resp = await client.get(
                url,
                headers={"User-Agent": "knowItAll/0.1"},
                follow_redirects=True,
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            logger.warning("Failed to fetch App Store reviews for app %s", app_id)
            continue

        entries = data.get("feed", {}).get("entry", [])
        if isinstance(entries, dict):
            entries = [entries]
        for entry in entries[:15]:
            title = ""
            content = ""
            if isinstance(entry.get("title"), dict):
                title = entry["title"].get("label", "")
            elif isinstance(entry.get("title"), str):
                title = entry["title"]
            if isinstance(entry.get("content"), dict):
                content = entry["content"].get("label", "")
            elif isinstance(entry.get("content"), str):
                content = entry["content"]

            text = f"{title} {content}".strip()
            if not text:
                continue
            lower = text.lower()
            hits = sum(1 for cue in pain_cues if cue in lower)
            if hits == 0:
                continue
            severity = min(hits / 3.0, 1.0)
            complaints.append(
                UserComplaint(
                    id=_hash_id("appstore", text),
                    summary=title[:200] if title else text[:200],
                    detail=content[:500],
                    source=ComplaintSource.APP_STORE,
                    source_url=f"https://apps.apple.com/us/app/id{app_id}",
                    quote=text[:200],
                    severity=round(severity, 2),
                    detected_at=datetime.now(timezone.utc),
                )
            )

    return complaints


# ---------------------------------------------------------------------------
# Google Play Reviews scanning
# ---------------------------------------------------------------------------

_GOOGLE_PLAY_APPS = [
    "com.twitter.android",
    "com.microsoft.office.outlook",
    "com.google.android.apps.authenticator2",
]


async def scan_google_play_reviews(
    client: httpx.AsyncClient,
    app_ids: list[str] | None = None,
) -> list[UserComplaint]:
    """Fetch Google Play store pages for popular tech apps and parse reviews."""
    complaints: list[UserComplaint] = []
    ids = app_ids or _GOOGLE_PLAY_APPS

    pain_cues = [
        "crash", "bug", "broken", "terrible", "worst", "hate",
        "frustrated", "useless", "slow", "awful", "disappointed",
    ]

    for app_id in ids:
        url = f"https://play.google.com/store/apps/details?id={app_id}&hl=en"
        try:
            resp = await client.get(
                url,
                headers={"User-Agent": "knowItAll/0.1"},
                follow_redirects=True,
                timeout=15.0,
            )
            resp.raise_for_status()
            html = resp.text
        except (httpx.HTTPError, ValueError):
            logger.warning("Failed to fetch Google Play reviews for %s", app_id)
            continue

        # Extract review-like text blocks from the page
        blocks = re.findall(r"<span[^>]*>(.*?)</span>", html, re.IGNORECASE | re.DOTALL)
        for block in blocks[:60]:
            text = re.sub(r"<[^>]+>", "", block).strip()
            if len(text) < 20:
                continue
            lower = text.lower()
            hits = sum(1 for cue in pain_cues if cue in lower)
            if hits == 0:
                continue
            severity = min(hits / 3.0, 1.0)
            complaints.append(
                UserComplaint(
                    id=_hash_id("gplay", text),
                    summary=text[:200],
                    detail=text[:500],
                    source=ComplaintSource.GOOGLE_PLAY,
                    source_url=url,
                    quote=text[:200],
                    severity=round(severity, 2),
                    detected_at=datetime.now(timezone.utc),
                )
            )

    return complaints


# ---------------------------------------------------------------------------
# Amazon Reviews scanning
# ---------------------------------------------------------------------------

_AMAZON_ELECTRONICS_URL = "https://www.amazon.com/Best-Sellers-Electronics/zgbs/electronics/"


async def scan_amazon_reviews(
    client: httpx.AsyncClient,
) -> list[UserComplaint]:
    """Fetch Amazon bestsellers in electronics/technology for complaints."""
    complaints: list[UserComplaint] = []
    try:
        resp = await client.get(
            _AMAZON_ELECTRONICS_URL,
            headers={"User-Agent": "knowItAll/0.1"},
            follow_redirects=True,
            timeout=15.0,
        )
        resp.raise_for_status()
        html = resp.text
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to scan Amazon bestsellers")
        return complaints

    blocks = re.findall(r"<span[^>]*>(.*?)</span>", html, re.IGNORECASE | re.DOTALL)
    pain_cues = [
        "broken", "terrible", "worst", "cheap", "waste",
        "defective", "disappointed", "poor", "problem", "junk",
    ]
    for block in blocks[:60]:
        text = re.sub(r"<[^>]+>", "", block).strip()
        if len(text) < 15:
            continue
        lower = text.lower()
        hits = sum(1 for cue in pain_cues if cue in lower)
        if hits == 0:
            continue
        severity = min(hits / 3.0, 1.0)
        complaints.append(
            UserComplaint(
                id=_hash_id("amazon", text),
                summary=text[:200],
                detail=text[:500],
                source=ComplaintSource.AMAZON,
                source_url=_AMAZON_ELECTRONICS_URL,
                quote=text[:200],
                severity=round(severity, 2),
                detected_at=datetime.now(timezone.utc),
            )
        )

    return complaints


# ---------------------------------------------------------------------------
# Forbes scanning
# ---------------------------------------------------------------------------

_FORBES_RSS = "https://www.forbes.com/innovation/feed/"


async def scan_forbes(
    client: httpx.AsyncClient,
) -> list[TechTrend]:
    """Fetch Forbes innovation RSS feed for tech trends."""
    trends: list[TechTrend] = []
    try:
        resp = await client.get(
            _FORBES_RSS,
            headers={"User-Agent": "knowItAll/0.1"},
            follow_redirects=True,
            timeout=15.0,
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:15]:
            title = entry.get("title", "").strip()
            if not title:
                continue
            link = entry.get("link", "https://www.forbes.com")
            summary = entry.get("summary", "").strip()[:300]
            trends.append(
                TechTrend(
                    id=_hash_id("forbes-trend", title),
                    title=title[:200],
                    description=summary or "Featured on Forbes Innovation.",
                    evidence="Published on Forbes Innovation feed.",
                    sources=[TrendSource.OTHER],
                    source_urls=[link],
                    interest_score=0.6,
                )
            )
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to scan Forbes")

    return trends


# ---------------------------------------------------------------------------
# Statista scanning
# ---------------------------------------------------------------------------

_STATISTA_URL = "https://www.statista.com/markets/418/technology-telecommunications/"


async def scan_statista(
    client: httpx.AsyncClient,
) -> list[TechTrend]:
    """Fetch Statista technology page for market insight trends."""
    trends: list[TechTrend] = []
    try:
        resp = await client.get(
            _STATISTA_URL,
            headers={"User-Agent": "knowItAll/0.1"},
            follow_redirects=True,
            timeout=15.0,
        )
        resp.raise_for_status()
        html = resp.text

        headings = re.findall(
            r"<h[1234][^>]*>(.*?)</h[1234]>", html, re.IGNORECASE | re.DOTALL,
        )
        for raw_title in headings[:20]:
            title = re.sub(r"<[^>]+>", "", raw_title).strip()
            if not title or len(title) < 3:
                continue
            trends.append(
                TechTrend(
                    id=_hash_id("statista", title),
                    title=title[:200],
                    description="Market insight from Statista.",
                    evidence="Found on Statista technology page.",
                    sources=[TrendSource.OTHER],
                    source_urls=[_STATISTA_URL],
                    interest_score=0.55,
                )
            )
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to scan Statista")

    return trends


# ---------------------------------------------------------------------------
# Crunchbase scanning
# ---------------------------------------------------------------------------

_CRUNCHBASE_URL = "https://www.crunchbase.com/discover/funding_rounds"


async def scan_crunchbase(
    client: httpx.AsyncClient,
) -> list[TechTrend]:
    """Fetch Crunchbase trending funding page for funding trends."""
    trends: list[TechTrend] = []
    try:
        resp = await client.get(
            _CRUNCHBASE_URL,
            headers={"User-Agent": "knowItAll/0.1"},
            follow_redirects=True,
            timeout=15.0,
        )
        resp.raise_for_status()
        html = resp.text

        # Extract company/funding names from links and headings
        entries = re.findall(
            r"<a[^>]+href=\"([^\"]*?)\"[^>]*>(.*?)</a>",
            html,
            re.IGNORECASE | re.DOTALL,
        )
        for href, raw_text in entries[:30]:
            title = re.sub(r"<[^>]+>", "", raw_text).strip()
            if not title or len(title) < 3:
                continue
            # Only include entries that look like company/funding mentions
            if "/organization/" not in href and "/funding_round/" not in href:
                continue
            link = href if href.startswith("http") else f"https://www.crunchbase.com{href}"
            trends.append(
                TechTrend(
                    id=_hash_id("cb-trend", title),
                    title=title[:200],
                    description="Trending funding activity on Crunchbase.",
                    evidence="Listed on Crunchbase funding rounds page.",
                    sources=[TrendSource.OTHER],
                    source_urls=[link],
                    interest_score=0.65,
                )
            )
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to scan Crunchbase")

    return trends


# ---------------------------------------------------------------------------
# CB Insights scanning
# ---------------------------------------------------------------------------

_CB_INSIGHTS_URL = "https://www.cbinsights.com/research/"


async def scan_cb_insights(
    client: httpx.AsyncClient,
) -> list[TechTrend]:
    """Fetch CB Insights research page for industry trends."""
    trends: list[TechTrend] = []
    try:
        resp = await client.get(
            _CB_INSIGHTS_URL,
            headers={"User-Agent": "knowItAll/0.1"},
            follow_redirects=True,
            timeout=15.0,
        )
        resp.raise_for_status()
        html = resp.text

        headings = re.findall(
            r"<h[23][^>]*>(.*?)</h[23]>", html, re.IGNORECASE | re.DOTALL,
        )
        for raw_title in headings[:20]:
            title = re.sub(r"<[^>]+>", "", raw_title).strip()
            if not title or len(title) < 5:
                continue
            trends.append(
                TechTrend(
                    id=_hash_id("cbi-trend", title),
                    title=title[:200],
                    description="Industry research from CB Insights.",
                    evidence="Found on CB Insights research page.",
                    sources=[TrendSource.OTHER],
                    source_urls=[_CB_INSIGHTS_URL],
                    interest_score=0.6,
                )
            )
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to scan CB Insights")

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

    # --- Community forums & social ---

    # Reddit
    reddit_complaints = await scan_reddit(client)
    all_complaints.extend(reddit_complaints)

    # Hacker News
    hn_trends, hn_complaints = await scan_hacker_news(client)
    all_trends.extend(hn_trends)
    all_complaints.extend(hn_complaints)

    # Twitter / X
    twitter_complaints = await scan_twitter(client)
    all_complaints.extend(twitter_complaints)

    # LinkedIn
    linkedin_complaints = await scan_linkedin(client)
    all_complaints.extend(linkedin_complaints)

    # --- Product & launch platforms ---

    # Product Hunt
    ph_trends = await scan_product_hunt(client)
    all_trends.extend(ph_trends)

    # --- Trend & research sources ---

    # Google Trends
    gt_trends = await scan_google_trends(client)
    all_trends.extend(gt_trends)

    # TechCrunch
    tc_trends = await scan_techcrunch(client)
    all_trends.extend(tc_trends)

    # Exploding Topics
    et_trends = await scan_exploding_topics(client)
    all_trends.extend(et_trends)

    # Y Combinator Requests for Startups
    yc_trends = await scan_yc_rfs(client)
    all_trends.extend(yc_trends)

    # Forbes Innovation
    forbes_trends = await scan_forbes(client)
    all_trends.extend(forbes_trends)

    # Statista
    statista_trends = await scan_statista(client)
    all_trends.extend(statista_trends)

    # Crunchbase
    cb_trends = await scan_crunchbase(client)
    all_trends.extend(cb_trends)

    # CB Insights
    cbi_trends = await scan_cb_insights(client)
    all_trends.extend(cbi_trends)

    # --- Review & complaint sites ---

    # Trustpilot
    tp_complaints = await scan_trustpilot(client)
    all_complaints.extend(tp_complaints)

    # Consumer Affairs
    ca_complaints = await scan_consumer_affairs(client)
    all_complaints.extend(ca_complaints)

    # BBB
    bbb_complaints = await scan_bbb(client)
    all_complaints.extend(bbb_complaints)

    # App Store Reviews
    appstore_complaints = await scan_app_store_reviews(client)
    all_complaints.extend(appstore_complaints)

    # Google Play Reviews
    gplay_complaints = await scan_google_play_reviews(client)
    all_complaints.extend(gplay_complaints)

    # Amazon Reviews
    amazon_complaints = await scan_amazon_reviews(client)
    all_complaints.extend(amazon_complaints)

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
