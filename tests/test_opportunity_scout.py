"""Tests for the opportunity scout service."""

from datetime import date

import pytest

from knowitall.models.scout_report import (
    ComplaintSource,
    IndustryGap,
    ScoutStartupIdea,
    SourceSummary,
    TechTrend,
    TrendSource,
    UserComplaint,
)
from knowitall.services.opportunity_scout import (
    build_source_summary,
    generate_ideas,
    identify_gaps,
)


def _make_trend(
    title: str = "AI Agents",
    interest: float = 0.8,
    evidence: str = "HN score: 300",
) -> TechTrend:
    return TechTrend(
        id="t-1",
        title=title,
        interest_score=interest,
        evidence=evidence,
        sources=[TrendSource.HACKER_NEWS],
    )


def _make_complaint(
    summary: str = "Product is broken",
    severity: float = 0.7,
    source: ComplaintSource = ComplaintSource.REDDIT,
) -> UserComplaint:
    return UserComplaint(
        id="c-1",
        summary=summary,
        severity=severity,
        source=source,
        quote=summary,
    )


class TestIdentifyGaps:
    def test_matching_trend_and_complaint(self):
        trends = [_make_trend(title="AI Agents framework")]
        complaints = [_make_complaint(summary="AI Agents are terrible and broken")]
        gaps = identify_gaps(trends, complaints)
        assert len(gaps) >= 1
        assert gaps[0].opportunity_score > 0

    def test_no_match_returns_fewer_gaps(self):
        trends = [_make_trend(title="Blockchain DeFi")]
        complaints = [_make_complaint(summary="Email client is terrible")]
        gaps = identify_gaps(trends, complaints)
        # Only cluster-based gaps, not cross-reference
        assert all("cluster" in g.id or "gap" in g.id for g in gaps)

    def test_severe_complaint_cluster(self):
        complaints = [
            _make_complaint(summary="CRM tool A sucks", severity=0.8),
            _make_complaint(summary="CRM tool B sucks too", severity=0.9),
        ]
        complaints[0].product_or_category = "CRM"
        complaints[0].id = "c-1"
        complaints[1].product_or_category = "CRM"
        complaints[1].id = "c-2"
        gaps = identify_gaps([], complaints)
        crm_gaps = [g for g in gaps if "CRM" in g.title]
        assert len(crm_gaps) == 1

    def test_empty_inputs(self):
        gaps = identify_gaps([], [])
        assert gaps == []


class TestGenerateIdeas:
    def test_generates_from_gaps(self):
        gaps = [
            IndustryGap(
                id="g-1",
                title="AI search gap",
                description="Users need better search.",
                demand_evidence="100 complaints",
                opportunity_score=0.8,
            )
        ]
        ideas = generate_ideas([], [], gaps)
        assert len(ideas) >= 1
        assert ideas[0].related_gap_ids == ["g-1"]

    def test_generates_from_trends(self):
        trends = [_make_trend(title="AI Agents")]
        ideas = generate_ideas(trends, [], [])
        assert len(ideas) >= 1
        assert ideas[0].related_trend_ids

    def test_generates_from_severe_complaints(self):
        complaints = [_make_complaint(summary="Auth system broken", severity=0.8)]
        ideas = generate_ideas([], complaints, [])
        assert len(ideas) >= 1
        assert ideas[0].related_complaint_ids

    def test_respects_max_ideas(self):
        gaps = [
            IndustryGap(
                id=f"g-{i}",
                title=f"Gap {i}",
                description="desc",
                demand_evidence="some",
                opportunity_score=0.8,
            )
            for i in range(20)
        ]
        ideas = generate_ideas([], [], gaps, max_ideas=3)
        assert len(ideas) <= 3

    def test_skips_low_severity_complaints(self):
        complaints = [_make_complaint(summary="Minor issue", severity=0.3)]
        ideas = generate_ideas([], complaints, [])
        assert len(ideas) == 0

    def test_skips_insignificant_trends(self):
        trends = [_make_trend(title="Minor thing", interest=0.3, evidence="")]
        ideas = generate_ideas(trends, [], [])
        assert len(ideas) == 0

    def test_deduplicates_ideas(self):
        gap = IndustryGap(
            id="g-1",
            title="Same gap",
            description="desc",
            demand_evidence="ev",
            opportunity_score=0.8,
        )
        ideas = generate_ideas([], [], [gap, gap])
        ids = [i.id for i in ideas]
        assert len(ids) == len(set(ids))


class TestBuildSourceSummary:
    def test_counts_sources(self):
        trends = [
            _make_trend(title="T1"),
            _make_trend(title="T2"),
        ]
        trends[1].id = "t-2"
        complaints = [_make_complaint()]
        summaries = build_source_summary(trends, complaints)
        assert len(summaries) > 0
        # Should have at least HN and Reddit
        names = [s.source_name.lower() for s in summaries]
        assert any("hacker" in n for n in names)
        assert any("reddit" in n for n in names)

    def test_adds_unavailable_sources(self):
        summaries = build_source_summary([], [])
        statuses = [s.status for s in summaries]
        assert "unavailable" in statuses

    def test_empty_inputs(self):
        summaries = build_source_summary([], [])
        assert len(summaries) > 0  # Mandatory sources still listed
