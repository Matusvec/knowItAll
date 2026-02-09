"""Zero-noise signal filtering service.

Enforces the principle: if it doesn't create leverage, reveal a timing
asymmetry, or unlock a new product class, it does not get sent.
"""

from __future__ import annotations

import logging

from knowitall.config import FilterConfig, get_config
from knowitall.models.paper import FounderLens, Paper
from knowitall.models.tool import HypeLevel, TechTool
from knowitall.models.opportunity import Opportunity
from knowitall.models.startup_idea import StartupIdea

logger = logging.getLogger(__name__)


def _paper_creates_leverage(paper: Paper) -> bool:
    """A paper creates leverage if it has high relevance or enables products."""
    return paper.founder_lens in (
        FounderLens.ENABLES_PRODUCT_CLASS,
        FounderLens.INFRASTRUCTURE_SHIFT,
        FounderLens.TIMING_ADVANTAGE,
    )


def _paper_reveals_timing(paper: Paper) -> bool:
    return paper.founder_lens == FounderLens.TIMING_ADVANTAGE


def _paper_unlocks_product_class(paper: Paper) -> bool:
    return paper.founder_lens == FounderLens.ENABLES_PRODUCT_CLASS


def filter_papers(
    papers: list[Paper],
    config: FilterConfig | None = None,
) -> list[Paper]:
    """Keep only papers that pass the zero-noise bar."""
    cfg = config or get_config().filters
    result: list[Paper] = []
    for p in papers:
        combined = (
            cfg.founder_relevance_weight * p.relevance_score
            + cfg.novelty_weight * p.novelty_score
            + cfg.timing_weight * (1.0 if _paper_reveals_timing(p) else 0.0)
        )
        if combined >= cfg.min_relevance_score or _paper_creates_leverage(p):
            result.append(p)
    return result


def filter_tools(tools: list[TechTool]) -> list[TechTool]:
    """Keep only tools that are genuine leverage shifts."""
    return [t for t in tools if t.is_signal()]


def filter_ideas(ideas: list[StartupIdea]) -> list[StartupIdea]:
    """Keep only ideas that are actionable and non-trivial."""
    return [i for i in ideas if i.is_actionable() and not i.not_worth_pursuing]


def filter_opportunities(opportunities: list[Opportunity]) -> list[Opportunity]:
    """Keep only high-priority opportunities."""
    return [o for o in opportunities if o.is_high_priority()]
