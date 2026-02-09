"""Tests for the startup translator service."""

import pytest

from knowitall.models.paper import FounderLens, Paper
from knowitall.models.startup_idea import Complexity, StartupSignal
from knowitall.services.startup_translator import (
    translate_paper_to_idea,
    translate_papers_to_ideas,
    _infer_tools,
    _infer_target_user,
)


def _make_paper(
    title: str = "Test Paper",
    abstract: str = "A test abstract.",
    founder_lens: FounderLens = FounderLens.ENABLES_PRODUCT_CLASS,
    relevance: float = 0.7,
    novelty: float = 0.5,
    **kwargs,
) -> Paper:
    return Paper(
        id="test-paper-1",
        title=title,
        abstract=abstract,
        founder_lens=founder_lens,
        relevance_score=relevance,
        novelty_score=novelty,
        problem_solved=abstract[:100],
        **kwargs,
    )


class TestInferTools:
    def test_llm_keywords(self):
        p = _make_paper(title="LLM-based Agent", abstract="Using GPT for language tasks.")
        tools = _infer_tools(p)
        assert any("LLM" in t for t in tools)

    def test_vision_keywords(self):
        p = _make_paper(title="Image Generation", abstract="A diffusion model for images.")
        tools = _infer_tools(p)
        assert any("Image" in t for t in tools)

    def test_retrieval_keywords(self):
        p = _make_paper(title="RAG System", abstract="Retrieval augmented generation.")
        tools = _infer_tools(p)
        assert any("Vector" in t for t in tools)

    def test_default_tools(self):
        p = _make_paper(title="Generic", abstract="Nothing special here.")
        tools = _infer_tools(p)
        assert len(tools) >= 1


class TestInferTargetUser:
    def test_medical(self):
        p = _make_paper(abstract="A medical imaging system for clinical diagnosis.")
        assert "Healthcare" in _infer_target_user(p)

    def test_developer(self):
        p = _make_paper(abstract="A code generation tool for developers.")
        assert "developer" in _infer_target_user(p).lower()

    def test_default(self):
        p = _make_paper(abstract="A general machine learning approach.")
        target = _infer_target_user(p)
        assert target  # non-empty


class TestTranslatePaperToIdea:
    def test_useless_paper_returns_none(self):
        p = _make_paper(founder_lens=FounderLens.USELESS)
        assert translate_paper_to_idea(p) is None

    def test_actionable_paper_returns_idea(self):
        p = _make_paper(
            title="Real-time LLM Agent",
            abstract="An open-source agent framework for language tasks.",
            founder_lens=FounderLens.ENABLES_PRODUCT_CLASS,
        )
        idea = translate_paper_to_idea(p)
        assert idea is not None
        assert idea.target_user != ""
        assert idea.build_timeline != ""
        assert len(idea.required_tools) > 0
        assert idea.is_actionable()

    def test_idea_includes_mvp_steps(self):
        p = _make_paper(founder_lens=FounderLens.TIMING_ADVANTAGE)
        idea = translate_paper_to_idea(p)
        assert idea is not None
        assert len(idea.mvp_steps) > 0

    def test_low_novelty_flags_not_worth(self):
        p = _make_paper(
            founder_lens=FounderLens.NICHE,
            novelty=0.2,
        )
        idea = translate_paper_to_idea(p)
        assert idea is not None
        assert idea.not_worth_pursuing != ""

    def test_market_signals_attached(self):
        p = _make_paper(founder_lens=FounderLens.ENABLES_PRODUCT_CLASS)
        signals = [StartupSignal(description="New API launch", source="twitter")]
        idea = translate_paper_to_idea(p, market_signals=signals)
        assert idea is not None
        assert len(idea.market_signals) == 1


class TestTranslatePapersToIdeas:
    def test_batch_translation(self):
        papers = [
            _make_paper(founder_lens=FounderLens.ENABLES_PRODUCT_CLASS),
            _make_paper(founder_lens=FounderLens.USELESS),
            _make_paper(founder_lens=FounderLens.TIMING_ADVANTAGE),
        ]
        # Unique ids needed
        papers[0].id = "p1"
        papers[1].id = "p2"
        papers[2].id = "p3"
        ideas = translate_papers_to_ideas(papers, max_ideas=5)
        # USELESS paper should be filtered out
        assert len(ideas) == 2

    def test_max_ideas_respected(self):
        papers = [
            _make_paper(founder_lens=FounderLens.ENABLES_PRODUCT_CLASS),
            _make_paper(founder_lens=FounderLens.TIMING_ADVANTAGE),
            _make_paper(founder_lens=FounderLens.INFRASTRUCTURE_SHIFT),
        ]
        for i, p in enumerate(papers):
            p.id = f"p{i}"
        ideas = translate_papers_to_ideas(papers, max_ideas=1)
        assert len(ideas) == 1
