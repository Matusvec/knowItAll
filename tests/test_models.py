"""Tests for data models."""

from datetime import date, datetime, timezone

from knowitall.models.paper import FounderLens, Paper
from knowitall.models.startup_idea import Complexity, StartupIdea, StartupSignal
from knowitall.models.tool import HypeLevel, TechTool
from knowitall.models.opportunity import Opportunity, OpportunityType
from knowitall.models.digest import ActionItem, DailyDigest, DigestSection


class TestPaper:
    def test_default_scores(self):
        p = Paper(id="test-1", title="Test Paper")
        assert p.relevance_score == 0.0
        assert p.novelty_score == 0.0

    def test_passes_noise_filter_below_threshold(self):
        p = Paper(id="test-1", title="Test", relevance_score=0.3, novelty_score=0.2)
        assert not p.passes_noise_filter(0.6)

    def test_passes_noise_filter_above_threshold(self):
        p = Paper(id="test-1", title="Test", relevance_score=0.8, novelty_score=0.7)
        assert p.passes_noise_filter(0.6)

    def test_passes_noise_filter_exact_threshold(self):
        p = Paper(id="test-1", title="Test", relevance_score=0.6, novelty_score=0.6)
        assert p.passes_noise_filter(0.6)

    def test_founder_lens_default(self):
        p = Paper(id="test-1", title="Test")
        assert p.founder_lens == FounderLens.USELESS


class TestStartupIdea:
    def test_is_actionable_complete(self):
        idea = StartupIdea(
            id="i-1",
            title="Test Idea",
            target_user="Developers",
            core_insight="A new approach",
            build_timeline="2 weeks",
            required_tools=["Python"],
        )
        assert idea.is_actionable()

    def test_is_actionable_missing_fields(self):
        idea = StartupIdea(id="i-1", title="Incomplete")
        assert not idea.is_actionable()

    def test_is_actionable_missing_tools(self):
        idea = StartupIdea(
            id="i-1",
            title="No Tools",
            target_user="Devs",
            core_insight="Something",
            build_timeline="1 week",
        )
        assert not idea.is_actionable()


class TestTechTool:
    def test_is_signal_genuine_shift(self):
        t = TechTool(id="t-1", name="Test", hype_level=HypeLevel.GENUINE_SHIFT)
        assert t.is_signal()

    def test_is_signal_game_changer(self):
        t = TechTool(id="t-1", name="Test", hype_level=HypeLevel.GAME_CHANGER)
        assert t.is_signal()

    def test_is_not_signal_incremental(self):
        t = TechTool(id="t-1", name="Test", hype_level=HypeLevel.INCREMENTAL)
        assert not t.is_signal()

    def test_is_not_signal_hype(self):
        t = TechTool(id="t-1", name="Test", hype_level=HypeLevel.PURE_HYPE)
        assert not t.is_signal()


class TestOpportunity:
    def test_is_high_priority(self):
        o = Opportunity(
            id="o-1",
            title="Test",
            opportunity_type=OpportunityType.HACKATHON,
            roi_score=0.8,
        )
        assert o.is_high_priority()

    def test_is_not_high_priority(self):
        o = Opportunity(
            id="o-1",
            title="Test",
            opportunity_type=OpportunityType.HACKATHON,
            roi_score=0.3,
        )
        assert not o.is_high_priority()


class TestDailyDigest:
    def test_total_signals_empty(self):
        d = DailyDigest(date=date.today())
        assert d.total_signals() == 0

    def test_total_signals_with_items(self):
        d = DailyDigest(
            date=date.today(),
            papers=[Paper(id="p1", title="P1")],
            tools=[TechTool(id="t1", name="T1")],
        )
        assert d.total_signals() == 2

    def test_build_sections_empty(self):
        d = DailyDigest(date=date.today())
        d.build_sections()
        assert d.sections == []

    def test_build_sections_with_papers(self):
        d = DailyDigest(
            date=date.today(),
            papers=[Paper(id="p1", title="P1"), Paper(id="p2", title="P2")],
        )
        d.build_sections()
        assert len(d.sections) == 1
        assert d.sections[0].title == "Research Signals"
        assert d.sections[0].items_count == 2

    def test_build_sections_all_types(self):
        d = DailyDigest(
            date=date.today(),
            papers=[Paper(id="p1", title="P1")],
            startup_ideas=[
                StartupIdea(id="i1", title="I1"),
            ],
            tools=[TechTool(id="t1", name="T1")],
            opportunities=[
                Opportunity(
                    id="o1",
                    title="O1",
                    opportunity_type=OpportunityType.HACKATHON,
                )
            ],
        )
        d.build_sections()
        assert len(d.sections) == 4
        titles = [s.title for s in d.sections]
        assert "Research Signals" in titles
        assert "Startup Ideas" in titles
        assert "Tech & Tools" in titles
        assert "Opportunity Radar" in titles
