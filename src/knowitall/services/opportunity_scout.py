"""Opportunity scout service.

Synthesizes signals from web scanning, trend analysis, and complaint
mining into a structured daily scout report with actionable startup ideas.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date

from knowitall.config import AppConfig, get_config
from knowitall.models.scout_report import (
    IndustryGap,
    ScoutReport,
    ScoutStartupIdea,
    SourceSummary,
    TechTrend,
    UserComplaint,
)

logger = logging.getLogger(__name__)


def _id(prefix: str, text: str) -> str:
    return f"{prefix}-{hashlib.sha256(text.encode()).hexdigest()[:10]}"


# ---------------------------------------------------------------------------
# Industry gap identification
# ---------------------------------------------------------------------------


def identify_gaps(
    trends: list[TechTrend],
    complaints: list[UserComplaint],
) -> list[IndustryGap]:
    """Cross-reference trends and complaints to identify industry gaps."""
    gaps: list[IndustryGap] = []

    # Strategy 1: high-interest trends with matching complaints
    for trend in trends:
        trend_words = set(trend.title.lower().split())
        matching_complaints = [
            c
            for c in complaints
            if c.is_actionable()
            and any(w in c.summary.lower() for w in trend_words if len(w) > 3)
        ]
        if matching_complaints:
            complaint_summaries = "; ".join(
                c.summary[:80] for c in matching_complaints[:3]
            )
            score = round(
                min(
                    (trend.interest_score + sum(c.severity for c in matching_complaints))
                    / (1 + len(matching_complaints)),
                    1.0,
                ),
                2,
            )
            gaps.append(
                IndustryGap(
                    id=_id("gap", trend.title),
                    title=f"Gap: {trend.title[:80]}",
                    description=(
                        f"Trend '{trend.title}' has high interest "
                        f"but users report pain points: {complaint_summaries}"
                    ),
                    demand_evidence=trend.evidence,
                    supply_assessment=(
                        f"{len(matching_complaints)} active complaints suggest "
                        f"current solutions are inadequate."
                    ),
                    opportunity_score=score,
                )
            )

    # Strategy 2: clusters of severe complaints without trend coverage
    severe = [c for c in complaints if c.severity >= 0.7]
    # Group by product/category where available
    categories: dict[str, list[UserComplaint]] = {}
    for c in severe:
        key = c.product_or_category or "general"
        categories.setdefault(key, []).append(c)
    for cat, cat_complaints in categories.items():
        if len(cat_complaints) >= 2:
            gaps.append(
                IndustryGap(
                    id=_id("gap-cluster", cat),
                    title=f"Complaint cluster: {cat}",
                    description=(
                        f"{len(cat_complaints)} severe complaints about '{cat}' "
                        f"suggest a significant unmet need."
                    ),
                    demand_evidence=f"{len(cat_complaints)} complaints with severity >= 0.7",
                    supply_assessment="Existing solutions failing to satisfy users.",
                    opportunity_score=round(
                        min(len(cat_complaints) / 5.0, 1.0), 2
                    ),
                )
            )

    # Sort by opportunity score
    gaps.sort(key=lambda g: g.opportunity_score, reverse=True)
    return gaps


# ---------------------------------------------------------------------------
# Startup idea generation
# ---------------------------------------------------------------------------

_TECH_STACKS = {
    "ai": ["Python", "FastAPI", "OpenAI API", "LangChain", "Pinecone"],
    "saas": ["Next.js", "PostgreSQL", "Stripe", "Vercel"],
    "mobile": ["React Native", "Firebase", "Stripe"],
    "data": ["Python", "Snowflake", "dbt", "Airflow"],
    "devtools": ["TypeScript", "VS Code Extension API", "GitHub API"],
}


def _infer_tech_stack(title: str, description: str) -> list[str]:
    """Infer a likely tech stack from the idea context."""
    text = f"{title} {description}".lower()
    for key, stack in _TECH_STACKS.items():
        if key in text:
            return stack
    return ["Python", "FastAPI", "PostgreSQL", "React"]


def generate_ideas(
    trends: list[TechTrend],
    complaints: list[UserComplaint],
    gaps: list[IndustryGap],
    max_ideas: int = 10,
) -> list[ScoutStartupIdea]:
    """Generate startup ideas by synthesizing trends, complaints, and gaps."""
    ideas: list[ScoutStartupIdea] = []

    # Idea source 1: from industry gaps
    for gap in gaps[:5]:
        title = f"Solution for: {gap.title[:60]}"
        desc = (
            f"Build a product addressing: {gap.description[:200]}. "
            f"Market evidence: {gap.demand_evidence[:100]}"
        )
        ideas.append(
            ScoutStartupIdea(
                id=_id("idea-gap", gap.title),
                title=title,
                description=desc,
                target_market=gap.supply_assessment[:100] or "Underserved users in this space",
                why_it_fills_gap=gap.description[:200],
                potential_impact=f"Opportunity score: {gap.opportunity_score}",
                tech_stack=_infer_tech_stack(title, desc),
                monetization="SaaS subscription or usage-based pricing",
                feasibility="medium",
                related_gap_ids=[gap.id],
            )
        )

    # Idea source 2: from high-interest trends
    for trend in trends[:5]:
        if not trend.is_significant():
            continue
        title = f"Capitalize on: {trend.title[:60]}"
        desc = (
            f"Leverage the rising trend of '{trend.title}' "
            f"(evidence: {trend.evidence[:100]}) to build a first-mover product."
        )
        ideas.append(
            ScoutStartupIdea(
                id=_id("idea-trend", trend.title),
                title=title,
                description=desc,
                target_market="Early adopters and tech-forward businesses",
                why_it_fills_gap=f"Trend is growing ({trend.growth_rate or 'rapidly'}) with limited solutions.",
                potential_impact=f"Interest score: {trend.interest_score}",
                tech_stack=_infer_tech_stack(title, desc),
                monetization="Freemium or API-based pricing",
                feasibility="medium",
                related_trend_ids=[trend.id],
            )
        )

    # Idea source 3: from severe complaints
    for complaint in complaints[:5]:
        if complaint.severity < 0.6:
            continue
        title = f"Fix: {complaint.summary[:60]}"
        desc = (
            f"Users are frustrated: '{complaint.quote[:150]}'. "
            f"Build a better alternative."
        )
        ideas.append(
            ScoutStartupIdea(
                id=_id("idea-complaint", complaint.summary),
                title=title,
                description=desc,
                target_market=complaint.product_or_category or "Frustrated users of existing tools",
                why_it_fills_gap=f"Severity: {complaint.severity}, source: {complaint.source.value}",
                potential_impact="High — directly addresses user pain point",
                tech_stack=_infer_tech_stack(title, desc),
                monetization="Subscription or one-time purchase",
                feasibility="medium",
                related_complaint_ids=[complaint.id],
            )
        )

    # Deduplicate and limit
    seen: set[str] = set()
    unique: list[ScoutStartupIdea] = []
    for idea in ideas:
        if idea.id not in seen:
            seen.add(idea.id)
            unique.append(idea)
    return unique[:max_ideas]


# ---------------------------------------------------------------------------
# Source tracking
# ---------------------------------------------------------------------------


def build_source_summary(
    trends: list[TechTrend],
    complaints: list[UserComplaint],
) -> list[SourceSummary]:
    """Summarize which sources were queried and what was found."""
    # Count items per source
    trend_sources: dict[str, int] = {}
    for t in trends:
        for src in t.sources:
            trend_sources[src.value] = trend_sources.get(src.value, 0) + 1

    complaint_sources: dict[str, int] = {}
    for c in complaints:
        complaint_sources[c.source.value] = (
            complaint_sources.get(c.source.value, 0) + 1
        )

    summaries: list[SourceSummary] = []

    _SOURCE_URLS = {
        "reddit": "https://www.reddit.com",
        "hacker_news": "https://news.ycombinator.com",
        "product_hunt": "https://www.producthunt.com",
        "google_trends": "https://trends.google.com",
        "exploding_topics": "https://explodingtopics.com",
        "twitter": "https://twitter.com",
        "linkedin": "https://www.linkedin.com",
        "trustpilot": "https://www.trustpilot.com",
        "consumer_affairs": "https://www.consumeraffairs.com",
        "bbb": "https://www.bbb.org",
        "techcrunch": "https://techcrunch.com",
        "app_store": "https://apps.apple.com",
        "google_play": "https://play.google.com",
        "amazon": "https://www.amazon.com",
        "other": "",
    }

    all_sources = set(trend_sources.keys()) | set(complaint_sources.keys())
    for src in sorted(all_sources):
        n_trends = trend_sources.get(src, 0)
        n_complaints = complaint_sources.get(src, 0)
        total = n_trends + n_complaints
        summaries.append(
            SourceSummary(
                source_name=src.replace("_", " ").title(),
                url=_SOURCE_URLS.get(src, ""),
                items_found=total,
                key_finding=f"{n_trends} trends, {n_complaints} complaints",
                status="success" if total > 0 else "partial",
            )
        )

    # Add mandatory sources that may not have been reached
    for src_name, url in _SOURCE_URLS.items():
        if src_name not in all_sources:
            summaries.append(
                SourceSummary(
                    source_name=src_name.replace("_", " ").title(),
                    url=url,
                    items_found=0,
                    key_finding="No data collected in this run.",
                    status="unavailable",
                )
            )

    return summaries


# ---------------------------------------------------------------------------
# Full scout report generation
# ---------------------------------------------------------------------------


async def generate_scout_report(
    config: AppConfig | None = None,
) -> ScoutReport:
    """Generate the full daily startup opportunity scout report."""
    import httpx as _httpx

    from knowitall.services.web_scanner import scan_all_sources

    cfg = config or get_config()

    async with _httpx.AsyncClient() as client:
        trends, complaints = await scan_all_sources(client, cfg)

    gaps = identify_gaps(trends, complaints)
    ideas = generate_ideas(
        trends,
        complaints,
        gaps,
        max_ideas=cfg.scout_max_ideas,
    )
    sources = build_source_summary(trends, complaints)

    # Apply limits
    trends = trends[: cfg.scout_max_trends]
    complaints = complaints[: cfg.scout_max_complaints]
    gaps = gaps[: cfg.scout_max_gaps]

    report = ScoutReport(
        date=date.today(),
        tech_trends=trends,
        complaints=complaints,
        industry_gaps=gaps,
        startup_ideas=ideas,
        sources_summary=sources,
    )
    report.build_headline()
    return report
