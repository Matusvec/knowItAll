"""Research signal detection service.

Monitors arXiv and OpenReview for AI/CS papers, enriches them with
founder-relevant analysis, and returns only high-signal results.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from xml.etree import ElementTree

import httpx

from knowitall.config import AppConfig, get_config
from knowitall.models.paper import FounderLens, Paper

logger = logging.getLogger(__name__)

ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}

# Keywords that boost founder relevance scoring
_FOUNDER_KEYWORDS = {
    "real-time",
    "efficient",
    "on-device",
    "edge",
    "low-latency",
    "production",
    "deployment",
    "api",
    "scalable",
    "fine-tuning",
    "few-shot",
    "zero-shot",
    "open-source",
    "benchmark",
    "faster",
    "cheaper",
    "lightweight",
    "distillation",
    "quantization",
    "retrieval",
    "agent",
    "tool-use",
    "multimodal",
}


def _compute_relevance(paper: Paper) -> float:
    """Score how relevant a paper is for founders (0-1)."""
    text = f"{paper.title} {paper.abstract}".lower()
    hits = sum(1 for kw in _FOUNDER_KEYWORDS if kw in text)
    raw = min(hits / 5.0, 1.0)
    # Boost papers with code
    if paper.code_url:
        raw = min(raw + 0.15, 1.0)
    return round(raw, 2)


def _compute_novelty(paper: Paper) -> float:
    """Heuristic novelty score based on abstract language cues."""
    novelty_cues = [
        "first",
        "novel",
        "state-of-the-art",
        "outperform",
        "new approach",
        "surpass",
        "breakthrough",
        "unprecedented",
    ]
    text = paper.abstract.lower()
    hits = sum(1 for cue in novelty_cues if cue in text)
    return round(min(hits / 3.0, 1.0), 2)


def _assign_founder_lens(paper: Paper) -> tuple[FounderLens, str]:
    """Determine the founder lens category and a short note."""
    text = f"{paper.title} {paper.abstract}".lower()

    if any(
        kw in text
        for kw in ("infrastructure", "serving", "deployment", "compiler", "runtime")
    ):
        return (
            FounderLens.INFRASTRUCTURE_SHIFT,
            "May shift underlying infra; evaluate if it reduces your serving costs.",
        )
    if any(
        kw in text for kw in ("real-time", "on-device", "edge", "low-latency", "fast")
    ):
        return (
            FounderLens.TIMING_ADVANTAGE,
            "Enables speed-dependent product classes that weren't viable before.",
        )
    if any(
        kw in text
        for kw in ("api", "tool-use", "agent", "plugin", "open-source", "fine-tun")
    ):
        return (
            FounderLens.ENABLES_PRODUCT_CLASS,
            "Directly enables a new category of products or integrations.",
        )
    if paper.relevance_score >= 0.4:
        return (
            FounderLens.NICHE,
            "Potentially useful for a narrow vertical application.",
        )
    return (
        FounderLens.USELESS,
        "Interesting research but no clear startup application right now.",
    )


def _parse_arxiv_entry(entry: ElementTree.Element) -> Paper:
    """Parse a single Atom entry element from the arXiv API."""
    ns = ARXIV_NS

    raw_id = entry.findtext("atom:id", default="", namespaces=ns)
    paper_id = raw_id.rsplit("/abs/", maxsplit=1)[-1] if "/abs/" in raw_id else raw_id

    title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
    title = " ".join(title.split())  # collapse whitespace

    abstract = (
        entry.findtext("atom:summary", default="", namespaces=ns) or ""
    ).strip()

    authors = [
        name.text.strip()
        for name in entry.findall("atom:author/atom:name", namespaces=ns)
        if name.text
    ]

    published_str = entry.findtext("atom:published", default="", namespaces=ns)
    published = None
    if published_str:
        try:
            published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
        except ValueError:
            pass

    categories = [
        cat.get("term", "")
        for cat in entry.findall("{http://arxiv.org/schemas/atom}category")
    ]

    pdf_url = ""
    for link in entry.findall("atom:link", namespaces=ns):
        if link.get("title") == "pdf":
            pdf_url = link.get("href", "")
            break

    return Paper(
        id=paper_id,
        title=title,
        authors=authors,
        abstract=abstract,
        published=published,
        source="arxiv",
        categories=categories,
        pdf_url=pdf_url,
        project_url=raw_id,
    )


async def fetch_arxiv_papers(
    client: httpx.AsyncClient,
    config: AppConfig | None = None,
) -> list[Paper]:
    """Fetch recent papers from arXiv across configured categories."""
    cfg = config or get_config()
    cat_query = "+OR+".join(f"cat:{c}" for c in cfg.sources.arxiv.categories)
    params = {
        "search_query": cat_query,
        "sortBy": cfg.sources.arxiv.sort_by,
        "sortOrder": cfg.sources.arxiv.sort_order,
        "max_results": str(cfg.sources.arxiv.max_results),
    }
    url = cfg.sources.arxiv.base_url
    try:
        resp = await client.get(url, params=params, timeout=30.0)
        resp.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Failed to fetch arXiv papers")
        return []

    return _parse_arxiv_response(resp.text)


def _parse_arxiv_response(xml_text: str) -> list[Paper]:
    """Parse the full arXiv Atom response into a list of papers."""
    try:
        root = ElementTree.fromstring(xml_text)  # noqa: S314
    except ElementTree.ParseError:
        logger.exception("Failed to parse arXiv XML")
        return []

    entries = root.findall("atom:entry", namespaces=ARXIV_NS)
    return [_parse_arxiv_entry(e) for e in entries]


def enrich_paper(paper: Paper) -> Paper:
    """Add scoring, founder lens, and summary to a paper."""
    paper.relevance_score = _compute_relevance(paper)
    paper.novelty_score = _compute_novelty(paper)
    paper.founder_lens, paper.founder_note = _assign_founder_lens(paper)

    # Build concise summary
    problem = paper.abstract[:200].split(". ")[0] if paper.abstract else ""
    paper.problem_solved = problem
    paper.why_it_matters = (
        f"Relevance: {paper.relevance_score}, Novelty: {paper.novelty_score}"
    )
    paper.summary = f"{paper.title}: {problem}"
    return paper


async def detect_research_signals(
    client: httpx.AsyncClient,
    config: AppConfig | None = None,
) -> list[Paper]:
    """Full pipeline: fetch, enrich, filter, and return high-signal papers."""
    cfg = config or get_config()
    papers = await fetch_arxiv_papers(client, cfg)
    enriched = [enrich_paper(p) for p in papers]
    filtered = [
        p
        for p in enriched
        if p.passes_noise_filter(cfg.filters.min_relevance_score)
    ]
    # Sort by combined score descending
    filtered.sort(
        key=lambda p: (p.relevance_score + p.novelty_score) / 2,
        reverse=True,
    )
    return filtered[: cfg.digest_max_papers]
