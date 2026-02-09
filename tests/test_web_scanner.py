"""Tests for the web scanner service."""

import json

import pytest
import httpx
import respx

from knowitall.models.scout_report import ComplaintSource, TrendSource
from knowitall.services.web_scanner import (
    scan_amazon_reviews,
    scan_app_store_reviews,
    scan_bbb,
    scan_cb_insights,
    scan_consumer_affairs,
    scan_crunchbase,
    scan_exploding_topics,
    scan_forbes,
    scan_google_play_reviews,
    scan_google_trends,
    scan_hacker_news,
    scan_linkedin,
    scan_product_hunt,
    scan_reddit,
    scan_statista,
    scan_techcrunch,
    scan_trustpilot,
    scan_twitter,
    scan_yc_rfs,
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
        respx.get("https://old.reddit.com/r/testSub/hot.json").mock(
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
        respx.get("https://old.reddit.com/r/failSub/hot.json").mock(
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
        respx.get("https://old.reddit.com/r/testSub/hot.json").mock(
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


class TestScanProductHunt:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_trends_from_rss(self):
        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Cool AI Tool</title>
              <link>https://www.producthunt.com/posts/cool-ai-tool</link>
            </item>
            <item>
              <title>New SaaS Platform</title>
              <link>https://www.producthunt.com/posts/new-saas-platform</link>
            </item>
          </channel>
        </rss>"""
        respx.get("https://www.producthunt.com/feed").mock(
            return_value=httpx.Response(200, text=rss_xml)
        )
        async with httpx.AsyncClient() as client:
            trends = await scan_product_hunt(client)
        assert len(trends) == 2
        assert trends[0].title == "Cool AI Tool"
        assert trends[1].title == "New SaaS Platform"
        assert all(TrendSource.PRODUCT_HUNT in t.sources for t in trends)

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        respx.get("https://www.producthunt.com/feed").mock(
            return_value=httpx.Response(500)
        )
        async with httpx.AsyncClient() as client:
            trends = await scan_product_hunt(client)
        assert trends == []


class TestScanGoogleTrends:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_trends_from_rss(self):
        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Generative AI</title>
              <link>https://trends.google.com/trends/trendingsearches/daily?geo=US#Generative+AI</link>
              <summary>Big surge in generative AI searches.</summary>
            </item>
            <item>
              <title>Quantum Computing Breakthrough</title>
              <link>https://trends.google.com/trends/trendingsearches/daily?geo=US#Quantum</link>
            </item>
          </channel>
        </rss>"""
        respx.get("https://trends.google.com/trending/rss?geo=US").mock(
            return_value=httpx.Response(200, text=rss_xml)
        )
        async with httpx.AsyncClient() as client:
            trends = await scan_google_trends(client)
        assert len(trends) == 2
        assert trends[0].title == "Generative AI"
        assert all(TrendSource.GOOGLE_TRENDS in t.sources for t in trends)

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        respx.get("https://trends.google.com/trending/rss?geo=US").mock(
            return_value=httpx.Response(500)
        )
        async with httpx.AsyncClient() as client:
            trends = await scan_google_trends(client)
        assert trends == []


class TestScanTechcrunch:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_trends_from_rss(self):
        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Startup raises $50M for AI platform</title>
              <link>https://techcrunch.com/2024/01/01/startup-ai/</link>
              <summary>A new startup just raised a big round.</summary>
            </item>
          </channel>
        </rss>"""
        respx.get("https://techcrunch.com/feed/").mock(
            return_value=httpx.Response(200, text=rss_xml)
        )
        async with httpx.AsyncClient() as client:
            trends = await scan_techcrunch(client)
        assert len(trends) == 1
        assert trends[0].title == "Startup raises $50M for AI platform"
        assert TrendSource.TECHCRUNCH in trends[0].sources

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        respx.get("https://techcrunch.com/feed/").mock(
            return_value=httpx.Response(500)
        )
        async with httpx.AsyncClient() as client:
            trends = await scan_techcrunch(client)
        assert trends == []


class TestScanExplodingTopics:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_trends_from_headings(self):
        html = """<html><body>
        <h2>AI Code Assistants</h2>
        <h3>Edge Computing Growth</h3>
        <h2>Synthetic Data Platforms</h2>
        </body></html>"""
        respx.get("https://explodingtopics.com/blog/trending-topics").mock(
            return_value=httpx.Response(200, text=html)
        )
        async with httpx.AsyncClient() as client:
            trends = await scan_exploding_topics(client)
        assert len(trends) == 3
        assert trends[0].title == "AI Code Assistants"
        assert all(TrendSource.EXPLODING_TOPICS in t.sources for t in trends)

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        respx.get("https://explodingtopics.com/blog/trending-topics").mock(
            return_value=httpx.Response(500)
        )
        async with httpx.AsyncClient() as client:
            trends = await scan_exploding_topics(client)
        assert trends == []


class TestScanTrustpilot:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_complaints(self):
        html = """<html><body>
        <p>This service is terrible and the worst experience I have ever had with tech support.</p>
        <p>Great product, love it!</p>
        <p>Absolutely awful, broken software that is a waste of money and very disappointing.</p>
        </body></html>"""
        respx.get("https://www.trustpilot.com/categories/technology_services").mock(
            return_value=httpx.Response(200, text=html)
        )
        async with httpx.AsyncClient() as client:
            complaints = await scan_trustpilot(client)
        assert len(complaints) >= 2
        assert all(c.source == ComplaintSource.TRUSTPILOT for c in complaints)

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        respx.get("https://www.trustpilot.com/categories/technology_services").mock(
            return_value=httpx.Response(500)
        )
        async with httpx.AsyncClient() as client:
            complaints = await scan_trustpilot(client)
        assert complaints == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_skips_non_complaint_content(self):
        html = """<html><body>
        <p>Everything works perfectly and we are happy customers with great results.</p>
        </body></html>"""
        respx.get("https://www.trustpilot.com/categories/technology_services").mock(
            return_value=httpx.Response(200, text=html)
        )
        async with httpx.AsyncClient() as client:
            complaints = await scan_trustpilot(client)
        assert len(complaints) == 0


class TestScanConsumerAffairs:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_complaints(self):
        html = """<html><body>
        <p>The product is terrible and broken beyond repair. Worst purchase I have ever made.</p>
        <p>Helpful article about choosing laptops.</p>
        </body></html>"""
        respx.get("https://www.consumeraffairs.com/computers/").mock(
            return_value=httpx.Response(200, text=html)
        )
        async with httpx.AsyncClient() as client:
            complaints = await scan_consumer_affairs(client)
        assert len(complaints) >= 1
        assert all(c.source == ComplaintSource.CONSUMER_AFFAIRS for c in complaints)

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        respx.get("https://www.consumeraffairs.com/computers/").mock(
            return_value=httpx.Response(500)
        )
        async with httpx.AsyncClient() as client:
            complaints = await scan_consumer_affairs(client)
        assert complaints == []


class TestScanBBB:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_complaints(self):
        html = """<html><body>
        <a href="/profile/software/acme-corp">Acme Corp - complaint filed for scam</a>
        <a href="/profile/software/good-co">Good Company</a>
        <a href="/profile/software/bad-inc">Bad Inc - terrible fraud reported</a>
        </body></html>"""
        respx.get(
            "https://www.bbb.org/search?find_type=category&category=Computer+Software"
        ).mock(return_value=httpx.Response(200, text=html))
        async with httpx.AsyncClient() as client:
            complaints = await scan_bbb(client)
        assert len(complaints) >= 2
        assert all(c.source == ComplaintSource.BBB for c in complaints)

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        respx.get(
            "https://www.bbb.org/search?find_type=category&category=Computer+Software"
        ).mock(return_value=httpx.Response(500))
        async with httpx.AsyncClient() as client:
            complaints = await scan_bbb(client)
        assert complaints == []


class TestScanYCRFS:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_trends_from_headings(self):
        html = """<html><body>
        <h1>Requests for Startups</h1>
        <h2>Better Enterprise Software</h2>
        <h2>AI for Healthcare</h2>
        </body></html>"""
        respx.get("https://www.ycombinator.com/rfs").mock(
            return_value=httpx.Response(200, text=html)
        )
        async with httpx.AsyncClient() as client:
            trends = await scan_yc_rfs(client)
        assert len(trends) == 3
        assert all(TrendSource.OTHER in t.sources for t in trends)

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        respx.get("https://www.ycombinator.com/rfs").mock(
            return_value=httpx.Response(500)
        )
        async with httpx.AsyncClient() as client:
            trends = await scan_yc_rfs(client)
        assert trends == []


class TestScanTwitter:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_complaints_with_token(self, monkeypatch):
        monkeypatch.setenv("TWITTER_BEARER_TOKEN", "test-token-123")
        api_response = {
            "data": [
                {
                    "id": "111",
                    "text": "This app is broken and terrible, I hate it so much",
                },
                {
                    "id": "222",
                    "text": "Love this new feature, works great!",
                },
                {
                    "id": "333",
                    "text": "Frustrated with the worst software update ever",
                },
            ]
        }
        respx.get("https://api.twitter.com/2/tweets/search/recent").mock(
            return_value=httpx.Response(200, json=api_response)
        )
        async with httpx.AsyncClient() as client:
            complaints = await scan_twitter(client)
        assert len(complaints) >= 2
        assert all(c.source == ComplaintSource.TWITTER for c in complaints)

    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_empty_without_token(self, monkeypatch):
        monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)
        async with httpx.AsyncClient() as client:
            complaints = await scan_twitter(client)
        assert complaints == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_api_error(self, monkeypatch):
        monkeypatch.setenv("TWITTER_BEARER_TOKEN", "test-token-123")
        respx.get("https://api.twitter.com/2/tweets/search/recent").mock(
            return_value=httpx.Response(500)
        )
        async with httpx.AsyncClient() as client:
            complaints = await scan_twitter(client)
        assert complaints == []


class TestScanLinkedIn:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_complaints_with_token(self, monkeypatch):
        monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "test-linkedin-token")
        api_response = {
            "elements": [
                {
                    "id": "post-1",
                    "commentary": "So frustrated with broken enterprise software, the worst problem in tech today",
                },
                {
                    "id": "post-2",
                    "commentary": "Excited about the new product launch!",
                },
            ]
        }
        respx.get("https://api.linkedin.com/v2/posts").mock(
            return_value=httpx.Response(200, json=api_response)
        )
        async with httpx.AsyncClient() as client:
            complaints = await scan_linkedin(client)
        assert len(complaints) >= 1
        assert all(c.source == ComplaintSource.LINKEDIN for c in complaints)

    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_empty_without_token(self, monkeypatch):
        monkeypatch.delenv("LINKEDIN_ACCESS_TOKEN", raising=False)
        async with httpx.AsyncClient() as client:
            complaints = await scan_linkedin(client)
        assert complaints == []


class TestScanAppStoreReviews:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_complaints_from_reviews(self):
        app_id = "12345"
        api_response = {
            "feed": {
                "entry": [
                    {
                        "title": {"label": "App keeps crashing"},
                        "content": {"label": "This app is broken and terrible. Worst update ever, so frustrated."},
                    },
                    {
                        "title": {"label": "Great app"},
                        "content": {"label": "Works perfectly, love it!"},
                    },
                ]
            }
        }
        respx.get(
            f"https://itunes.apple.com/us/rss/customerreviews/page=1/id={app_id}/sortby=mostrecent/json"
        ).mock(return_value=httpx.Response(200, json=api_response))
        async with httpx.AsyncClient() as client:
            complaints = await scan_app_store_reviews(client, app_ids=[app_id])
        assert len(complaints) >= 1
        assert all(c.source == ComplaintSource.APP_STORE for c in complaints)

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        app_id = "99999"
        respx.get(
            f"https://itunes.apple.com/us/rss/customerreviews/page=1/id={app_id}/sortby=mostrecent/json"
        ).mock(return_value=httpx.Response(500))
        async with httpx.AsyncClient() as client:
            complaints = await scan_app_store_reviews(client, app_ids=[app_id])
        assert complaints == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_custom_app_ids(self):
        api_response = {
            "feed": {
                "entry": [
                    {
                        "title": {"label": "Useless and slow"},
                        "content": {"label": "Broken bug-ridden awful crash fest."},
                    },
                ]
            }
        }
        respx.get(
            "https://itunes.apple.com/us/rss/customerreviews/page=1/id=CUSTOM1/sortby=mostrecent/json"
        ).mock(return_value=httpx.Response(200, json=api_response))
        respx.get(
            "https://itunes.apple.com/us/rss/customerreviews/page=1/id=CUSTOM2/sortby=mostrecent/json"
        ).mock(return_value=httpx.Response(200, json=api_response))
        async with httpx.AsyncClient() as client:
            complaints = await scan_app_store_reviews(client, app_ids=["CUSTOM1", "CUSTOM2"])
        assert len(complaints) >= 2


class TestScanGooglePlayReviews:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_complaints_from_html(self):
        app_id = "com.example.app"
        html = """<html><body>
        <span>This app is broken and terrible, the worst update made it crash constantly.</span>
        <span>Works great!</span>
        <span>So frustrated, useless after the latest bug introduced awful performance.</span>
        </body></html>"""
        respx.get(
            f"https://play.google.com/store/apps/details?id={app_id}&hl=en"
        ).mock(return_value=httpx.Response(200, text=html))
        async with httpx.AsyncClient() as client:
            complaints = await scan_google_play_reviews(client, app_ids=[app_id])
        assert len(complaints) >= 2
        assert all(c.source == ComplaintSource.GOOGLE_PLAY for c in complaints)

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        app_id = "com.fail.app"
        respx.get(
            f"https://play.google.com/store/apps/details?id={app_id}&hl=en"
        ).mock(return_value=httpx.Response(500))
        async with httpx.AsyncClient() as client:
            complaints = await scan_google_play_reviews(client, app_ids=[app_id])
        assert complaints == []


class TestScanAmazonReviews:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_complaints_from_html(self):
        html = """<html><body>
        <span>This product is broken and terrible, worst purchase of my life and such a waste.</span>
        <span>Good quality item</span>
        <span>Defective junk, very disappointed with poor build quality.</span>
        </body></html>"""
        respx.get(
            "https://www.amazon.com/Best-Sellers-Electronics/zgbs/electronics/"
        ).mock(return_value=httpx.Response(200, text=html))
        async with httpx.AsyncClient() as client:
            complaints = await scan_amazon_reviews(client)
        assert len(complaints) >= 2
        assert all(c.source == ComplaintSource.AMAZON for c in complaints)

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        respx.get(
            "https://www.amazon.com/Best-Sellers-Electronics/zgbs/electronics/"
        ).mock(return_value=httpx.Response(500))
        async with httpx.AsyncClient() as client:
            complaints = await scan_amazon_reviews(client)
        assert complaints == []


class TestScanForbes:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_trends_from_rss(self):
        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>The Future Of AI In Business</title>
              <link>https://www.forbes.com/sites/ai-business/</link>
              <summary>AI is transforming business operations.</summary>
            </item>
          </channel>
        </rss>"""
        respx.get("https://www.forbes.com/innovation/feed/").mock(
            return_value=httpx.Response(200, text=rss_xml)
        )
        async with httpx.AsyncClient() as client:
            trends = await scan_forbes(client)
        assert len(trends) == 1
        assert trends[0].title == "The Future Of AI In Business"
        assert TrendSource.OTHER in trends[0].sources

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        respx.get("https://www.forbes.com/innovation/feed/").mock(
            return_value=httpx.Response(500)
        )
        async with httpx.AsyncClient() as client:
            trends = await scan_forbes(client)
        assert trends == []


class TestScanStatista:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_trends_from_headings(self):
        html = """<html><body>
        <h2>Global Smartphone Market</h2>
        <h3>Cloud Computing Revenue</h3>
        </body></html>"""
        respx.get(
            "https://www.statista.com/markets/418/technology-telecommunications/"
        ).mock(return_value=httpx.Response(200, text=html))
        async with httpx.AsyncClient() as client:
            trends = await scan_statista(client)
        assert len(trends) == 2
        assert all(TrendSource.OTHER in t.sources for t in trends)

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        respx.get(
            "https://www.statista.com/markets/418/technology-telecommunications/"
        ).mock(return_value=httpx.Response(500))
        async with httpx.AsyncClient() as client:
            trends = await scan_statista(client)
        assert trends == []


class TestScanCrunchbase:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_trends_from_html(self):
        html = """<html><body>
        <a href="/organization/acme-ai">Acme AI</a>
        <a href="/funding_round/series-a-xyz">Series A for XYZ Corp</a>
        <a href="/about">About Crunchbase</a>
        </body></html>"""
        respx.get("https://www.crunchbase.com/discover/funding_rounds").mock(
            return_value=httpx.Response(200, text=html)
        )
        async with httpx.AsyncClient() as client:
            trends = await scan_crunchbase(client)
        # Only /organization/ and /funding_round/ links are included
        assert len(trends) == 2
        assert all(TrendSource.OTHER in t.sources for t in trends)

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        respx.get("https://www.crunchbase.com/discover/funding_rounds").mock(
            return_value=httpx.Response(500)
        )
        async with httpx.AsyncClient() as client:
            trends = await scan_crunchbase(client)
        assert trends == []


class TestScanCBInsights:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extracts_trends_from_headings(self):
        html = """<html><body>
        <h2>State of Fintech Report</h2>
        <h3>Healthcare AI Trends 2024</h3>
        <h3>ab</h3>
        </body></html>"""
        respx.get("https://www.cbinsights.com/research/").mock(
            return_value=httpx.Response(200, text=html)
        )
        async with httpx.AsyncClient() as client:
            trends = await scan_cb_insights(client)
        # "ab" is < 5 chars so should be skipped
        assert len(trends) == 2
        assert trends[0].title == "State of Fintech Report"
        assert all(TrendSource.OTHER in t.sources for t in trends)

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        respx.get("https://www.cbinsights.com/research/").mock(
            return_value=httpx.Response(500)
        )
        async with httpx.AsyncClient() as client:
            trends = await scan_cb_insights(client)
        assert trends == []
