"""Tests for the research monitor service."""

from datetime import datetime, timezone

import pytest

from knowitall.models.paper import FounderLens, Paper
from knowitall.services.research_monitor import (
    _compute_novelty,
    _compute_relevance,
    _assign_founder_lens,
    _parse_arxiv_response,
    enrich_paper,
)


SAMPLE_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>ArXiv Query</title>
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <title>Real-time Efficient LLM Agent for Edge Deployment</title>
    <summary>We present a novel real-time agent framework for edge deployment
    that outperforms state-of-the-art methods. This open-source tool enables
    low-latency API serving with fine-tuning support.</summary>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <published>2024-01-15T00:00:00Z</published>
    <link href="http://arxiv.org/abs/2401.00001v1" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2401.00001v1" rel="related"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.00002v1</id>
    <title>Theoretical Analysis of Convex Optimization</title>
    <summary>We provide a theoretical analysis of convergence rates in
    convex optimization problems under standard assumptions.</summary>
    <author><name>Charlie Brown</name></author>
    <published>2024-01-15T00:00:00Z</published>
    <link href="http://arxiv.org/abs/2401.00002v1" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2401.00002v1" rel="related"/>
  </entry>
</feed>
"""


class TestComputeRelevance:
    def test_high_relevance_paper(self):
        p = Paper(
            id="test",
            title="Real-time Efficient LLM Agent",
            abstract="A scalable open-source agent for edge deployment with fine-tuning and API support.",
        )
        score = _compute_relevance(p)
        assert score >= 0.6

    def test_low_relevance_paper(self):
        p = Paper(
            id="test",
            title="Theoretical Analysis",
            abstract="We study convergence rates under standard assumptions.",
        )
        score = _compute_relevance(p)
        assert score < 0.4

    def test_code_url_boosts_score(self):
        p = Paper(
            id="test",
            title="Some Paper",
            abstract="An agent for deployment.",
            code_url="https://github.com/test/repo",
        )
        score_with_code = _compute_relevance(p)
        p.code_url = ""
        score_without = _compute_relevance(p)
        assert score_with_code > score_without


class TestComputeNovelty:
    def test_high_novelty(self):
        p = Paper(
            id="test",
            title="Test",
            abstract="This is the first novel approach that outperforms state-of-the-art.",
        )
        score = _compute_novelty(p)
        assert score >= 0.6

    def test_low_novelty(self):
        p = Paper(
            id="test",
            title="Test",
            abstract="We apply existing methods to a new dataset.",
        )
        score = _compute_novelty(p)
        assert score < 0.4


class TestAssignFounderLens:
    def test_infrastructure_shift(self):
        p = Paper(
            id="test",
            title="New Runtime Infrastructure",
            abstract="A new serving deployment system.",
            relevance_score=0.5,
        )
        lens, note = _assign_founder_lens(p)
        assert lens == FounderLens.INFRASTRUCTURE_SHIFT

    def test_timing_advantage(self):
        p = Paper(
            id="test",
            title="Real-time Edge Processing",
            abstract="Low-latency processing on device.",
            relevance_score=0.5,
        )
        lens, note = _assign_founder_lens(p)
        assert lens == FounderLens.TIMING_ADVANTAGE

    def test_enables_product_class(self):
        p = Paper(
            id="test",
            title="Tool-Use Agent with Open-Source API",
            abstract="An agent that uses tools via API.",
            relevance_score=0.5,
        )
        lens, note = _assign_founder_lens(p)
        assert lens == FounderLens.ENABLES_PRODUCT_CLASS

    def test_useless(self):
        p = Paper(
            id="test",
            title="Convergence Theory",
            abstract="Pure theoretical analysis.",
            relevance_score=0.1,
        )
        lens, note = _assign_founder_lens(p)
        assert lens == FounderLens.USELESS


class TestParseArxivResponse:
    def test_parse_two_entries(self):
        papers = _parse_arxiv_response(SAMPLE_ARXIV_XML)
        assert len(papers) == 2

    def test_first_paper_fields(self):
        papers = _parse_arxiv_response(SAMPLE_ARXIV_XML)
        p = papers[0]
        assert p.id == "2401.00001v1"
        assert "Real-time" in p.title
        assert len(p.authors) == 2
        assert p.source == "arxiv"
        assert p.pdf_url == "http://arxiv.org/pdf/2401.00001v1"

    def test_invalid_xml_returns_empty(self):
        papers = _parse_arxiv_response("not xml at all")
        assert papers == []


class TestEnrichPaper:
    def test_enrich_adds_scores(self):
        p = Paper(
            id="test",
            title="Real-time Agent",
            abstract="A novel scalable open-source agent for edge deployment.",
        )
        enriched = enrich_paper(p)
        assert enriched.relevance_score > 0
        assert enriched.novelty_score >= 0
        assert enriched.summary != ""
        assert enriched.founder_lens is not None
