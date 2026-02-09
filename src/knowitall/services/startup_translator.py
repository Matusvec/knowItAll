"""Research-to-startup translation service.

Combines research papers with market signals to generate concrete,
actionable startup ideas — not fluff.
"""

from __future__ import annotations

import hashlib
import logging

from knowitall.models.paper import FounderLens, Paper
from knowitall.models.startup_idea import Complexity, StartupIdea, StartupSignal

logger = logging.getLogger(__name__)

# Maps founder lens → base complexity
_LENS_COMPLEXITY: dict[FounderLens, Complexity] = {
    FounderLens.ENABLES_PRODUCT_CLASS: Complexity.MEDIUM,
    FounderLens.INFRASTRUCTURE_SHIFT: Complexity.HARD,
    FounderLens.TIMING_ADVANTAGE: Complexity.LOW,
    FounderLens.NICHE: Complexity.MEDIUM,
    FounderLens.USELESS: Complexity.HARD,
}

_TIMELINE: dict[Complexity, str] = {
    Complexity.LOW: "2-4 weeks",
    Complexity.MEDIUM: "1-3 months",
    Complexity.HARD: "3-6 months",
}


def _idea_id(paper_id: str, suffix: str = "") -> str:
    raw = f"{paper_id}:{suffix}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _infer_tools(paper: Paper) -> list[str]:
    """Infer likely required tools based on paper categories and content."""
    tools: list[str] = []
    text = f"{paper.title} {paper.abstract}".lower()
    if "language" in text or "llm" in text or "gpt" in text:
        tools.append("LLM API (OpenAI / Anthropic / open-source)")
    if "vision" in text or "image" in text or "diffusion" in text:
        tools.append("Image model (Stable Diffusion / DALL-E)")
    if "retrieval" in text or "rag" in text:
        tools.append("Vector DB (Pinecone / Weaviate / Chroma)")
    if "fine-tun" in text:
        tools.append("Fine-tuning infra (LoRA / QLoRA)")
    if "agent" in text or "tool-use" in text:
        tools.append("Agent framework (LangChain / AutoGen)")
    if "real-time" in text or "stream" in text:
        tools.append("Streaming infra (WebSockets / SSE)")
    if not tools:
        tools.append("Python + FastAPI")
    return tools


def _infer_target_user(paper: Paper) -> str:
    """Infer the likely target user from paper content."""
    text = f"{paper.title} {paper.abstract}".lower()
    if "medical" in text or "health" in text or "clinical" in text:
        return "Healthcare professionals / clinics"
    if "legal" in text or "law" in text or "contract" in text:
        return "Legal teams / solo practitioners"
    if "code" in text or "developer" in text or "programming" in text:
        return "Software developers / engineering teams"
    if "education" in text or "student" in text or "learning" in text:
        return "Educators / edtech platforms"
    if "enterprise" in text or "business" in text:
        return "Enterprise teams / B2B SaaS buyers"
    return "Technical founders / AI-native startups"


def translate_paper_to_idea(
    paper: Paper,
    market_signals: list[StartupSignal] | None = None,
) -> StartupIdea | None:
    """Generate a startup idea from a paper, if it warrants one.

    Returns None for papers with no startup potential.
    """
    if paper.founder_lens == FounderLens.USELESS:
        return None

    signals = market_signals or []
    complexity = _LENS_COMPLEXITY.get(paper.founder_lens, Complexity.MEDIUM)
    tools = _infer_tools(paper)
    target = _infer_target_user(paper)

    idea = StartupIdea(
        id=_idea_id(paper.id, "idea"),
        title=f"Startup from: {paper.title[:80]}",
        target_user=target,
        core_insight=paper.problem_solved or paper.abstract[:200],
        defensibility=_infer_defensibility(paper),
        complexity=complexity,
        build_timeline=_TIMELINE[complexity],
        required_tools=tools,
        paper_ids=[paper.id],
        market_signals=signals,
        not_worth_pursuing=_flag_not_worth(paper),
        why_not=_flag_why_not(paper),
        mvp_steps=_generate_mvp_steps(paper, tools),
        pitch_hook=f"Using {paper.title[:50]}… to solve [{target}]'s core pain.",
    )
    return idea


def _infer_defensibility(paper: Paper) -> str:
    """Suggest where defensibility might come from."""
    text = paper.abstract.lower()
    if "data" in text:
        return "Proprietary data pipeline or domain-specific dataset."
    if "fine-tun" in text:
        return "Fine-tuned model on proprietary data — hard to replicate without similar data."
    if "infra" in text or "system" in text:
        return "Infrastructure moat — high switching cost once integrated."
    return "Execution speed and first-mover timing advantage."


def _flag_not_worth(paper: Paper) -> str:
    if paper.novelty_score < 0.3:
        return "Incremental improvement over existing methods."
    return ""


def _flag_why_not(paper: Paper) -> str:
    if paper.novelty_score < 0.3:
        return "Low novelty score indicates marginal gains over state of the art."
    return ""


def _generate_mvp_steps(paper: Paper, tools: list[str]) -> list[str]:
    """Generate concrete MVP steps."""
    steps = [
        f"1. Validate core assumption: reproduce key result from {paper.id}.",
        f"2. Set up stack: {', '.join(tools[:3])}.",
        "3. Build minimal proof-of-concept for 1 target user.",
        "4. Get 5 real users to test within 2 weeks.",
        "5. Measure retention / NPS before building further.",
    ]
    return steps


def translate_papers_to_ideas(
    papers: list[Paper],
    market_signals: list[StartupSignal] | None = None,
    max_ideas: int = 5,
) -> list[StartupIdea]:
    """Batch-translate papers into startup ideas, returning only actionable ones."""
    ideas: list[StartupIdea] = []
    for paper in papers:
        idea = translate_paper_to_idea(paper, market_signals)
        if idea and idea.is_actionable():
            ideas.append(idea)
        if len(ideas) >= max_ideas:
            break
    return ideas
