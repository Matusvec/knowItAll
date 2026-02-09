"""API routes for the knowItAll daily intelligence assistant."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import httpx

from knowitall.config import get_config
from knowitall.models.digest import ActionItem, DailyDigest
from knowitall.services import (
    research_monitor,
    startup_translator,
    tool_tracker,
    opportunity_radar,
    signal_filter,
)

router = APIRouter()

# Templates are resolved relative to the package
import pathlib

_TEMPLATE_DIR = pathlib.Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))


def _build_actions(digest: DailyDigest) -> list[ActionItem]:
    """Generate follow-up action items for every digest entry."""
    actions: list[ActionItem] = []
    for idea in digest.startup_ideas:
        actions.extend(
            [
                ActionItem(
                    label="Generate an MVP plan",
                    action_type="mvp_plan",
                    target_id=idea.id,
                    description=f"Create a step-by-step MVP plan for: {idea.title}",
                ),
                ActionItem(
                    label="Assess competition",
                    action_type="competition_assessment",
                    target_id=idea.id,
                    description=f"Analyze competitive landscape for: {idea.title}",
                ),
                ActionItem(
                    label="Estimate costs",
                    action_type="cost_estimate",
                    target_id=idea.id,
                    description=f"Break down build/run costs for: {idea.title}",
                ),
                ActionItem(
                    label="Draft a pitch outline",
                    action_type="pitch_outline",
                    target_id=idea.id,
                    description=f"Create an investor-ready pitch for: {idea.title}",
                ),
            ]
        )
    return actions


@router.get("/api/digest", response_model=DailyDigest)
async def get_digest() -> DailyDigest:
    """Generate today's daily intelligence digest (JSON)."""
    cfg = get_config()
    async with httpx.AsyncClient() as client:
        papers = await research_monitor.detect_research_signals(client, cfg)
        tools = await tool_tracker.detect_tool_signals(client, cfg)

    ideas = startup_translator.translate_papers_to_ideas(
        papers, max_ideas=cfg.digest_max_ideas
    )
    opportunities = opportunity_radar.build_opportunity_radar(
        papers, tools, max_opportunities=cfg.digest_max_opportunities
    )

    # Apply zero-noise filter
    papers = signal_filter.filter_papers(papers, cfg.filters)
    tools = signal_filter.filter_tools(tools)
    ideas = signal_filter.filter_ideas(ideas)
    opportunities = signal_filter.filter_opportunities(opportunities)

    digest = DailyDigest(
        date=date.today(),
        headline=f"knowItAll — {date.today().strftime('%B %d, %Y')}",
        papers=papers,
        startup_ideas=ideas,
        tools=tools,
        opportunities=opportunities,
    )
    digest.actions = _build_actions(digest)
    digest.build_sections()
    return digest


@router.get("/", response_class=HTMLResponse)
async def digest_page(request: Request) -> HTMLResponse:
    """Render the interactive daily digest as an HTML page."""
    digest = await get_digest()
    return templates.TemplateResponse(
        "digest.html",
        {"request": request, "digest": digest},
    )


@router.get("/api/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "service": "knowItAll", "version": "0.1.0"}
