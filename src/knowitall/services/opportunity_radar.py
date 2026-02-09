"""Founder opportunity radar service.

Surfaces hackathons, accelerators, grants, competitions, and strategic
timing windows, prioritised by ROI, resume value, and speed to validation.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from knowitall.models.opportunity import Opportunity, OpportunityType
from knowitall.models.paper import Paper
from knowitall.models.tool import TechTool

logger = logging.getLogger(__name__)


def _opp_id(title: str) -> str:
    return hashlib.sha256(title.encode()).hexdigest()[:12]


def generate_timing_opportunities(
    papers: list[Paper],
    tools: list[TechTool],
) -> list[Opportunity]:
    """Generate strategic timing opportunities from today's signals.

    These are "new model/tool makes X suddenly viable" windows.
    """
    opportunities: list[Opportunity] = []

    for paper in papers:
        if paper.relevance_score < 0.6:
            continue
        opp = Opportunity(
            id=_opp_id(f"timing-{paper.id}"),
            title=f"Timing window: {paper.title[:60]}",
            opportunity_type=OpportunityType.STRATEGIC_TIMING,
            description=(
                f"Paper '{paper.title}' creates a timing advantage. "
                f"The technique can be applied before competitors catch up."
            ),
            url=paper.pdf_url or paper.project_url,
            roi_score=round((paper.relevance_score + paper.novelty_score) / 2, 2),
            speed_to_validation="Weeks — apply the technique to an existing product.",
            timing_note=f"First-mover window: act within 2-4 weeks of publication.",
            action_steps=[
                "Read the paper and reproduce the key result.",
                "Identify the highest-value application in your domain.",
                "Build a minimal prototype and share with 5 target users.",
            ],
        )
        opportunities.append(opp)

    for tool in tools:
        if not tool.is_signal():
            continue
        opp = Opportunity(
            id=_opp_id(f"timing-{tool.id}"),
            title=f"Tool launch window: {tool.name[:60]}",
            opportunity_type=OpportunityType.STRATEGIC_TIMING,
            description=(
                f"New tool '{tool.name}' ({tool.hype_level.value}) — "
                f"early adopters get disproportionate leverage."
            ),
            url=tool.url,
            roi_score=tool.leverage_score,
            speed_to_validation="Days — integrate and ship a demo.",
            timing_note="Launch-day adoption window. Build something visible now.",
            action_steps=[
                f"Read docs: {tool.docs_url or tool.url}",
                "Build a minimal demo using the tool.",
                "Share on Twitter / HN for early visibility.",
            ],
        )
        opportunities.append(opp)

    return opportunities


def score_opportunity(opp: Opportunity) -> Opportunity:
    """Refine opportunity scoring based on type and attributes."""
    base = opp.roi_score
    if opp.opportunity_type == OpportunityType.HACKATHON:
        base = max(base, 0.5)
    elif opp.opportunity_type == OpportunityType.GRANT:
        base = min(base + 0.1, 1.0)
    elif opp.opportunity_type == OpportunityType.ACCELERATOR:
        base = min(base + 0.15, 1.0)
    opp.roi_score = round(base, 2)
    return opp


def build_opportunity_radar(
    papers: list[Paper],
    tools: list[TechTool],
    external_opportunities: list[Opportunity] | None = None,
    max_opportunities: int = 5,
) -> list[Opportunity]:
    """Full pipeline: generate and rank founder opportunities."""
    timing = generate_timing_opportunities(papers, tools)
    external = external_opportunities or []
    all_opps = [score_opportunity(o) for o in timing + external]
    all_opps.sort(key=lambda o: o.roi_score, reverse=True)
    return all_opps[:max_opportunities]
