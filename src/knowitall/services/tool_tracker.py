"""Tech & tool awareness tracking service.

Tracks new AI tools, frameworks, model releases, APIs, and infra changes,
and explains whether each is hype or a genuine leverage shift.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

import httpx

from knowitall.config import AppConfig, get_config
from knowitall.models.tool import HypeLevel, TechTool

logger = logging.getLogger(__name__)


def _tool_id(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()[:12]


def _assess_hype(tool: TechTool) -> tuple[HypeLevel, str]:
    """Classify a tool as hype or genuine shift."""
    text = f"{tool.name} {tool.description}".lower()

    if any(kw in text for kw in ("revolutionary", "agi", "solves everything")):
        return HypeLevel.PURE_HYPE, "Marketing language without technical substance."

    if any(
        kw in text
        for kw in ("10x", "order of magnitude", "replaces", "eliminates", "paradigm")
    ):
        return (
            HypeLevel.GAME_CHANGER,
            "Significant capability jump; worth immediate evaluation.",
        )

    if any(
        kw in text
        for kw in ("open-source", "production-ready", "benchmark", "state-of-the-art")
    ):
        return (
            HypeLevel.GENUINE_SHIFT,
            "Tangible improvement backed by reproducible results.",
        )

    return HypeLevel.INCREMENTAL, "Useful but not a paradigm shift."


def _compute_leverage(tool: TechTool) -> float:
    """Score how much leverage this tool gives a founder."""
    score = 0.0
    if tool.hype_level == HypeLevel.GAME_CHANGER:
        score += 0.5
    elif tool.hype_level == HypeLevel.GENUINE_SHIFT:
        score += 0.35
    elif tool.hype_level == HypeLevel.INCREMENTAL:
        score += 0.15

    if tool.docs_url:
        score += 0.1
    if tool.demo_url:
        score += 0.1
    if tool.use_cases:
        score += min(len(tool.use_cases) * 0.05, 0.2)

    return round(min(score, 1.0), 2)


def enrich_tool(tool: TechTool) -> TechTool:
    """Add hype assessment and leverage score to a tool."""
    tool.hype_level, tool.hype_rationale = _assess_hype(tool)
    tool.leverage_score = _compute_leverage(tool)
    return tool


async def fetch_huggingface_models(
    client: httpx.AsyncClient,
    config: AppConfig | None = None,
) -> list[TechTool]:
    """Fetch recently released models from Hugging Face."""
    cfg = config or get_config()
    url = f"{cfg.sources.hf_url}/models"
    params = {"sort": "lastModified", "direction": "-1", "limit": "20"}

    try:
        resp = await client.get(url, params=params, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("Failed to fetch HuggingFace models")
        return []

    tools: list[TechTool] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("modelId", item.get("id", ""))
        if not name:
            continue
        tool = TechTool(
            id=_tool_id(name),
            name=name,
            category="model",
            url=f"https://huggingface.co/{name}",
            description=item.get("pipeline_tag", ""),
        )
        tools.append(tool)
    return tools


async def detect_tool_signals(
    client: httpx.AsyncClient,
    config: AppConfig | None = None,
) -> list[TechTool]:
    """Full pipeline: fetch, enrich, and return genuine tool signals."""
    cfg = config or get_config()
    raw_tools = await fetch_huggingface_models(client, cfg)
    enriched = [enrich_tool(t) for t in raw_tools]
    signals = [t for t in enriched if t.is_signal()]
    signals.sort(key=lambda t: t.leverage_score, reverse=True)
    return signals[: cfg.digest_max_tools]
