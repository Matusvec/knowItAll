"""Paper model representing a research publication signal."""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field


class FounderLens(str, enum.Enum):
    """Assessment of a paper's startup relevance."""

    USELESS = "useless_for_startups"
    NICHE = "niche_application"
    ENABLES_PRODUCT_CLASS = "enables_product_class"
    INFRASTRUCTURE_SHIFT = "infrastructure_shift"
    TIMING_ADVANTAGE = "timing_advantage"


class Paper(BaseModel):
    """A research paper with founder-relevant analysis."""

    id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: str = ""
    published: datetime | None = None
    source: str = ""  # e.g. "arxiv", "openreview"
    categories: list[str] = Field(default_factory=list)

    # Direct links
    pdf_url: str = ""
    code_url: str = ""
    project_url: str = ""

    # Analysis fields
    summary: str = ""
    problem_solved: str = ""
    why_it_matters: str = ""
    whats_new: str = ""
    founder_lens: FounderLens = FounderLens.USELESS
    founder_note: str = ""

    # Scoring
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    novelty_score: float = Field(default=0.0, ge=0.0, le=1.0)

    def passes_noise_filter(self, min_score: float = 0.6) -> bool:
        """Return True if this paper passes the zero-noise threshold."""
        combined = (self.relevance_score + self.novelty_score) / 2
        return combined >= min_score
