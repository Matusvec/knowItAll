"""Configuration management for knowItAll."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field


class ArxivConfig(BaseModel):
    """Configuration for arXiv feed monitoring."""

    base_url: str = "https://export.arxiv.org/api/query"
    categories: list[str] = Field(
        default_factory=lambda: [
            "cs.AI",
            "cs.LG",
            "cs.CL",
            "cs.CV",
            "cs.CR",
            "stat.ML",
        ]
    )
    max_results: int = 50
    sort_by: str = "submittedDate"
    sort_order: str = "descending"


class SourcesConfig(BaseModel):
    """Configuration for all monitored sources."""

    arxiv: ArxivConfig = Field(default_factory=ArxivConfig)
    openreview_url: str = "https://api.openreview.net"
    github_trending_url: str = "https://api.github.com"
    hf_url: str = "https://huggingface.co/api"


class FilterConfig(BaseModel):
    """Configuration for zero-noise signal filtering."""

    min_relevance_score: float = 0.6
    founder_relevance_weight: float = 0.4
    novelty_weight: float = 0.3
    timing_weight: float = 0.3


class ScoutConfig(BaseModel):
    """Configuration for the startup opportunity scout."""

    reddit_subreddits: list[str] = Field(
        default_factory=lambda: [
            "Entrepreneur",
            "startups",
            "smallbusiness",
            "SaaS",
            "artificial",
        ]
    )
    hn_max_stories: int = 30
    min_complaint_severity: float = 0.5
    min_trend_interest: float = 0.5


class EmailConfig(BaseModel):
    """Configuration for email delivery."""

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    recipient: str = "matusvec@gmail.com"
    sender: str = ""


class SchedulerConfig(BaseModel):
    """Configuration for the daily scan scheduler."""

    scan_hour: int = 5
    scan_minute: int = 30
    email_hour: int = 6
    email_minute: int = 0


class AppConfig(BaseModel):
    """Top-level application configuration."""

    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    filters: FilterConfig = Field(default_factory=FilterConfig)
    scout: ScoutConfig = Field(default_factory=ScoutConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    digest_max_papers: int = 10
    digest_max_tools: int = 5
    digest_max_opportunities: int = 5
    digest_max_ideas: int = 5
    scout_max_trends: int = 5
    scout_max_complaints: int = 10
    scout_max_gaps: int = 5
    scout_max_ideas: int = 10


def get_config() -> AppConfig:
    """Return the application configuration."""
    return AppConfig(
        email=EmailConfig(
            smtp_host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(os.environ.get("SMTP_PORT", "587")),
            smtp_user=os.environ.get("SMTP_USER", ""),
            smtp_password=os.environ.get("SMTP_PASSWORD", ""),
            recipient=os.environ.get("EMAIL_RECIPIENT", "matusvec@gmail.com"),
            sender=os.environ.get("SMTP_SENDER", os.environ.get("SMTP_USER", "")),
        ),
    )
