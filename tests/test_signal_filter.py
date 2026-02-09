"""Tests for the zero-noise signal filter service."""

import pytest

from knowitall.config import FilterConfig
from knowitall.models.paper import FounderLens, Paper
from knowitall.models.tool import HypeLevel, TechTool
from knowitall.models.startup_idea import StartupIdea
from knowitall.models.opportunity import Opportunity, OpportunityType
from knowitall.services.signal_filter import (
    filter_papers,
    filter_tools,
    filter_ideas,
    filter_opportunities,
)


class TestFilterPapers:
    def test_keeps_high_relevance_paper(self):
        p = Paper(
            id="p1",
            title="Good",
            relevance_score=0.9,
            novelty_score=0.8,
            founder_lens=FounderLens.ENABLES_PRODUCT_CLASS,
        )
        result = filter_papers([p])
        assert len(result) == 1

    def test_removes_low_score_useless_paper(self):
        p = Paper(
            id="p1",
            title="Bad",
            relevance_score=0.1,
            novelty_score=0.1,
            founder_lens=FounderLens.USELESS,
        )
        result = filter_papers([p])
        assert len(result) == 0

    def test_keeps_leverage_paper_even_lower_score(self):
        p = Paper(
            id="p1",
            title="Infra",
            relevance_score=0.3,
            novelty_score=0.3,
            founder_lens=FounderLens.INFRASTRUCTURE_SHIFT,
        )
        result = filter_papers([p])
        assert len(result) == 1

    def test_custom_filter_config(self):
        cfg = FilterConfig(min_relevance_score=0.9)
        p = Paper(
            id="p1",
            title="Moderate",
            relevance_score=0.5,
            novelty_score=0.5,
            founder_lens=FounderLens.NICHE,
        )
        result = filter_papers([p], config=cfg)
        assert len(result) == 0


class TestFilterTools:
    def test_keeps_genuine_shift(self):
        t = TechTool(id="t1", name="Good", hype_level=HypeLevel.GENUINE_SHIFT)
        assert len(filter_tools([t])) == 1

    def test_removes_hype(self):
        t = TechTool(id="t1", name="Hype", hype_level=HypeLevel.PURE_HYPE)
        assert len(filter_tools([t])) == 0

    def test_removes_incremental(self):
        t = TechTool(id="t1", name="Inc", hype_level=HypeLevel.INCREMENTAL)
        assert len(filter_tools([t])) == 0


class TestFilterIdeas:
    def test_keeps_actionable_idea(self):
        idea = StartupIdea(
            id="i1",
            title="Good Idea",
            target_user="Devs",
            core_insight="Something new",
            build_timeline="2 weeks",
            required_tools=["Python"],
        )
        assert len(filter_ideas([idea])) == 1

    def test_removes_non_actionable(self):
        idea = StartupIdea(id="i1", title="Incomplete")
        assert len(filter_ideas([idea])) == 0

    def test_removes_flagged_not_worth(self):
        idea = StartupIdea(
            id="i1",
            title="Flagged",
            target_user="Devs",
            core_insight="Something",
            build_timeline="2 weeks",
            required_tools=["Python"],
            not_worth_pursuing="Incremental improvement.",
        )
        assert len(filter_ideas([idea])) == 0


class TestFilterOpportunities:
    def test_keeps_high_priority(self):
        o = Opportunity(
            id="o1",
            title="Good",
            opportunity_type=OpportunityType.HACKATHON,
            roi_score=0.8,
        )
        assert len(filter_opportunities([o])) == 1

    def test_removes_low_priority(self):
        o = Opportunity(
            id="o1",
            title="Low",
            opportunity_type=OpportunityType.HACKATHON,
            roi_score=0.3,
        )
        assert len(filter_opportunities([o])) == 0
