"""Tests for scout report data models."""

from datetime import date

from knowitall.models.scout_report import (
    ComplaintSource,
    IndustryGap,
    ScoutReport,
    ScoutStartupIdea,
    SourceSummary,
    TechTrend,
    TrendSource,
    UserComplaint,
)


class TestTechTrend:
    def test_is_significant_true(self):
        t = TechTrend(
            id="t1", title="AI Agents", interest_score=0.7, evidence="HN score: 200"
        )
        assert t.is_significant()

    def test_is_significant_low_score(self):
        t = TechTrend(
            id="t1", title="Minor thing", interest_score=0.3, evidence="some"
        )
        assert not t.is_significant()

    def test_is_significant_no_evidence(self):
        t = TechTrend(id="t1", title="AI Agents", interest_score=0.7)
        assert not t.is_significant()

    def test_defaults(self):
        t = TechTrend(id="t1", title="Test")
        assert t.interest_score == 0.0
        assert t.sources == []


class TestUserComplaint:
    def test_is_actionable_true(self):
        c = UserComplaint(id="c1", summary="Product X is broken", severity=0.8)
        assert c.is_actionable()

    def test_is_actionable_low_severity(self):
        c = UserComplaint(id="c1", summary="Minor issue", severity=0.3)
        assert not c.is_actionable()

    def test_is_actionable_empty_summary(self):
        c = UserComplaint(id="c1", summary="", severity=0.8)
        assert not c.is_actionable()


class TestIndustryGap:
    def test_is_viable_true(self):
        g = IndustryGap(
            id="g1",
            title="Gap",
            opportunity_score=0.7,
            demand_evidence="100 complaints",
        )
        assert g.is_viable()

    def test_is_viable_low_score(self):
        g = IndustryGap(
            id="g1", title="Gap", opportunity_score=0.3, demand_evidence="some"
        )
        assert not g.is_viable()

    def test_is_viable_no_evidence(self):
        g = IndustryGap(id="g1", title="Gap", opportunity_score=0.7)
        assert not g.is_viable()


class TestScoutReport:
    def test_total_signals_empty(self):
        r = ScoutReport(date=date.today())
        assert r.total_signals() == 0

    def test_total_signals_with_items(self):
        r = ScoutReport(
            date=date.today(),
            tech_trends=[TechTrend(id="t1", title="T1")],
            complaints=[UserComplaint(id="c1", summary="C1")],
            industry_gaps=[IndustryGap(id="g1", title="G1")],
            startup_ideas=[ScoutStartupIdea(id="i1", title="I1")],
        )
        assert r.total_signals() == 4

    def test_build_headline_with_items(self):
        r = ScoutReport(
            date=date(2026, 2, 9),
            tech_trends=[TechTrend(id="t1", title="T1")],
            complaints=[
                UserComplaint(id="c1", summary="C1"),
                UserComplaint(id="c2", summary="C2"),
            ],
            startup_ideas=[ScoutStartupIdea(id="i1", title="I1")],
        )
        r.build_headline()
        assert "1 trends" in r.headline
        assert "2 complaints" in r.headline
        assert "1 ideas" in r.headline
        assert "February 09, 2026" in r.headline

    def test_build_headline_empty(self):
        r = ScoutReport(date=date(2026, 2, 9))
        r.build_headline()
        assert "No signals" in r.headline


class TestSourceSummary:
    def test_fields(self):
        s = SourceSummary(
            source_name="Reddit",
            url="https://reddit.com",
            items_found=5,
            key_finding="3 trends, 2 complaints",
            status="success",
        )
        assert s.source_name == "Reddit"
        assert s.items_found == 5
