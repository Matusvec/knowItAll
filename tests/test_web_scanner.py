"""Tests for the web scanner service."""

import json

import pytest
import httpx
import respx

from knowitall.models.scout_report import ComplaintSource, TrendSource
from knowitall.services.web_scanner import (
    scan_hacker_news,
    scan_reddit,
)


@pytest.fixture
def mock_reddit_response():
    """Sample Reddit API response."""
    return {
        "data": {
            "children": [
                {
                    "data": {
                        "title": "I hate this product — it's broken and frustrating",
                        "selftext": "The product keeps crashing. Need a better alternative.",
                        "permalink": "/r/startups/comments/abc/test/",
                    }
                },
                {
                    "data": {
                        "title": "Great new SaaS tool launched today",
                        "selftext": "Check it out, works perfectly.",
                        "permalink": "/r/startups/comments/def/saas/",
                    }
                },
                {
                    "data": {
                        "title": "Frustrated with the terrible CRM options available",
                        "selftext": "Why is there no good CRM for small teams?",
                        "permalink": "/r/startups/comments/ghi/crm/",
                    }
                },
            ]
        }
    }


@pytest.fixture
def mock_hn_stories():
    """Sample HN top stories and items."""
    return {
        "top": [101, 102, 103],
        "items": {
            101: {
                "id": 101,
                "title": "Show HN: New AI framework for building agents",
                "url": "https://example.com/agents",
                "score": 200,
            },
            102: {
                "id": 102,
                "title": "Why the current auth systems are broken",
                "url": "https://example.com/auth",
                "score": 80,
            },
            103: {
                "id": 103,
                "title": "Random low-score post",
                "url": "https://example.com/rand",
                "score": 5,
            },
        },
    }


class TestScanReddit:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_complaints(self, mock_reddit_response):
        respx.get("https://www.reddit.com/r/testSub/hot.json").mock(
            return_value=httpx.Response(200, json=mock_reddit_response)
        )
        async with httpx.AsyncClient() as client:
            complaints = await scan_reddit(client, subreddits=["testSub"])
        # Should find at least 2 complaint-like posts (ones with pain keywords)
        assert len(complaints) >= 2
        assert all(c.source == ComplaintSource.REDDIT for c in complaints)

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        respx.get("https://www.reddit.com/r/failSub/hot.json").mock(
            return_value=httpx.Response(500)
        )
        async with httpx.AsyncClient() as client:
            complaints = await scan_reddit(client, subreddits=["failSub"])
        assert complaints == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_skips_non_complaint_posts(self, mock_reddit_response):
        # Only the positive post
        data = {
            "data": {
                "children": [mock_reddit_response["data"]["children"][1]]
            }
        }
        respx.get("https://www.reddit.com/r/testSub/hot.json").mock(
            return_value=httpx.Response(200, json=data)
        )
        async with httpx.AsyncClient() as client:
            complaints = await scan_reddit(client, subreddits=["testSub"])
        assert len(complaints) == 0


class TestScanHackerNews:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_trends_and_complaints(self, mock_hn_stories):
        respx.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json"
        ).mock(return_value=httpx.Response(200, json=mock_hn_stories["top"]))

        for sid, item in mock_hn_stories["items"].items():
            respx.get(
                f"https://hacker-news.firebaseio.com/v0/item/{sid}.json"
            ).mock(return_value=httpx.Response(200, json=item))

        async with httpx.AsyncClient() as client:
            trends, complaints = await scan_hacker_news(client, max_stories=3)

        # Story 101 has "ai" + score >= 50 → should be a trend
        assert len(trends) >= 1
        assert any("AI" in t.title or "ai" in t.title.lower() for t in trends)

        # Story 102 has "broken" → should be a complaint
        assert len(complaints) >= 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_api_failure(self):
        respx.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json"
        ).mock(return_value=httpx.Response(500))

        async with httpx.AsyncClient() as client:
            trends, complaints = await scan_hacker_news(client)
        assert trends == []
        assert complaints == []
