"""Tests for the opportunity radar service."""

import pytest

from knowitall.models.paper import FounderLens, Paper
from knowitall.models.tool import HypeLevel, TechTool
from knowitall.models.opportunity import Opportunity, OpportunityType
from knowitall.services.opportunity_radar import (
    generate_timing_opportunities,
    score_opportunity,
    build_opportunity_radar,
)


def _make_paper(relevance: float = 0.8, novelty: float = 0.7) -> Paper:
    return Paper(
        id="p-1",
        title="Relevant Paper",
        relevance_score=relevance,
        novelty_score=novelty,
        pdf_url="http://example.com/paper.pdf",
    )


def _make_tool(is_signal: bool = True) -> TechTool:
    return TechTool(
        id="t-1",
        name="SuperTool",
        hype_level=HypeLevel.GENUINE_SHIFT if is_signal else HypeLevel.INCREMENTAL,
        leverage_score=0.8 if is_signal else 0.2,
        url="http://example.com/tool",
    )


class TestGenerateTimingOpportunities:
    def test_generates_from_relevant_paper(self):
        opps = generate_timing_opportunities([_make_paper()], [])
        assert len(opps) == 1
        assert opps[0].opportunity_type == OpportunityType.STRATEGIC_TIMING

    def test_skips_low_relevance_paper(self):
        opps = generate_timing_opportunities([_make_paper(relevance=0.3)], [])
        assert len(opps) == 0

    def test_generates_from_signal_tool(self):
        opps = generate_timing_opportunities([], [_make_tool(is_signal=True)])
        assert len(opps) == 1

    def test_skips_non_signal_tool(self):
        opps = generate_timing_opportunities([], [_make_tool(is_signal=False)])
        assert len(opps) == 0

    def test_combines_papers_and_tools(self):
        opps = generate_timing_opportunities(
            [_make_paper()],
            [_make_tool()],
        )
        assert len(opps) == 2


class TestScoreOpportunity:
    def test_hackathon_min_score(self):
        o = Opportunity(
            id="o-1",
            title="Hackathon",
            opportunity_type=OpportunityType.HACKATHON,
            roi_score=0.2,
        )
        scored = score_opportunity(o)
        assert scored.roi_score >= 0.5

    def test_grant_boost(self):
        o = Opportunity(
            id="o-1",
            title="Grant",
            opportunity_type=OpportunityType.GRANT,
            roi_score=0.6,
        )
        scored = score_opportunity(o)
        assert scored.roi_score == 0.7

    def test_accelerator_boost(self):
        o = Opportunity(
            id="o-1",
            title="Accelerator",
            opportunity_type=OpportunityType.ACCELERATOR,
            roi_score=0.6,
        )
        scored = score_opportunity(o)
        assert scored.roi_score == 0.75


class TestBuildOpportunityRadar:
    def test_returns_sorted_list(self):
        opps = build_opportunity_radar([_make_paper()], [_make_tool()])
        assert len(opps) >= 1
        # Verify descending order
        for i in range(len(opps) - 1):
            assert opps[i].roi_score >= opps[i + 1].roi_score

    def test_respects_max(self):
        papers = [_make_paper(), _make_paper()]
        papers[1].id = "p-2"
        tools = [_make_tool(), _make_tool()]
        tools[1].id = "t-2"
        opps = build_opportunity_radar(papers, tools, max_opportunities=2)
        assert len(opps) <= 2

    def test_includes_external_opportunities(self):
        external = [
            Opportunity(
                id="ext-1",
                title="External Grant",
                opportunity_type=OpportunityType.GRANT,
                roi_score=0.9,
            )
        ]
        opps = build_opportunity_radar([], [], external_opportunities=external)
        assert len(opps) == 1
        assert opps[0].id == "ext-1"
