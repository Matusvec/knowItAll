"""Tests for the tool tracker service."""

import pytest

from knowitall.models.tool import HypeLevel, TechTool
from knowitall.services.tool_tracker import (
    _assess_hype,
    _compute_leverage,
    enrich_tool,
)


def _make_tool(
    name: str = "TestTool",
    description: str = "A test tool.",
    **kwargs,
) -> TechTool:
    return TechTool(id="t-1", name=name, description=description, **kwargs)


class TestAssessHype:
    def test_pure_hype(self):
        t = _make_tool(description="This revolutionary AGI solves everything.")
        level, _ = _assess_hype(t)
        assert level == HypeLevel.PURE_HYPE

    def test_game_changer(self):
        t = _make_tool(description="10x improvement that replaces existing systems.")
        level, _ = _assess_hype(t)
        assert level == HypeLevel.GAME_CHANGER

    def test_genuine_shift(self):
        t = _make_tool(description="Open-source state-of-the-art benchmark results.")
        level, _ = _assess_hype(t)
        assert level == HypeLevel.GENUINE_SHIFT

    def test_incremental(self):
        t = _make_tool(description="Minor update to an existing library.")
        level, _ = _assess_hype(t)
        assert level == HypeLevel.INCREMENTAL


class TestComputeLeverage:
    def test_game_changer_high_leverage(self):
        t = _make_tool(hype_level=HypeLevel.GAME_CHANGER, docs_url="http://docs", demo_url="http://demo")
        score = _compute_leverage(t)
        assert score >= 0.7

    def test_incremental_low_leverage(self):
        t = _make_tool(hype_level=HypeLevel.INCREMENTAL)
        score = _compute_leverage(t)
        assert score <= 0.3

    def test_use_cases_boost(self):
        t = _make_tool(
            hype_level=HypeLevel.GENUINE_SHIFT,
            use_cases=["case1", "case2", "case3"],
        )
        score = _compute_leverage(t)
        t2 = _make_tool(hype_level=HypeLevel.GENUINE_SHIFT)
        score2 = _compute_leverage(t2)
        assert score > score2


class TestEnrichTool:
    def test_enrich_adds_hype_and_score(self):
        t = _make_tool(name="FastModel", description="Open-source production-ready benchmark model.")
        enriched = enrich_tool(t)
        assert enriched.hype_level is not None
        assert enriched.hype_rationale != ""
        assert enriched.leverage_score > 0
