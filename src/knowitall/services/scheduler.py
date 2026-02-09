"""Background scheduler for daily scans and email delivery."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

import httpx
from apscheduler.schedulers.background import BackgroundScheduler

from knowitall.config import AppConfig, get_config
from knowitall.models.digest import DailyDigest
from knowitall.models.scout_report import ScoutReport
from knowitall.services import (
    research_monitor,
    startup_translator,
    tool_tracker,
    opportunity_radar,
    signal_filter,
)
from knowitall.services.email_service import send_digest_email
from knowitall.services.opportunity_scout import generate_scout_report

logger = logging.getLogger(__name__)

# In-memory store for the latest scan results.
# This is shared with the API routes so manual "send email" can work.
latest_digest: DailyDigest | None = None
latest_scout: ScoutReport | None = None

_scheduler: BackgroundScheduler | None = None


async def _run_scan(cfg: AppConfig) -> tuple[DailyDigest, ScoutReport]:
    """Execute a full scan and return (digest, scout_report)."""
    async with httpx.AsyncClient() as client:
        papers = await research_monitor.detect_research_signals(client, cfg)
        tools = await tool_tracker.detect_tool_signals(client, cfg)

    ideas = startup_translator.translate_papers_to_ideas(
        papers, max_ideas=cfg.digest_max_ideas
    )
    opportunities = opportunity_radar.build_opportunity_radar(
        papers, tools, max_opportunities=cfg.digest_max_opportunities
    )

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
    digest.build_sections()

    scout = await generate_scout_report()
    return digest, scout


def run_scheduled_scan() -> None:
    """Synchronous wrapper called by the scheduler to run the morning scan."""
    global latest_digest, latest_scout
    logger.info("Scheduled scan starting …")
    cfg = get_config()
    try:
        loop = asyncio.new_event_loop()
        digest, scout = loop.run_until_complete(_run_scan(cfg))
        loop.close()
        latest_digest = digest
        latest_scout = scout
        logger.info(
            "Scheduled scan complete — %d signals in digest, %d in scout",
            digest.total_signals(),
            scout.total_signals(),
        )
    except Exception:
        logger.exception("Scheduled scan failed")


def run_scheduled_email() -> None:
    """Send the latest scan results via email (called by the scheduler)."""
    if latest_digest is None:
        logger.warning("No scan results available — skipping scheduled email.")
        return
    cfg = get_config()
    send_digest_email(latest_digest, cfg.email, scout_report=latest_scout)


def start_scheduler(cfg: AppConfig | None = None) -> BackgroundScheduler:
    """Start the APScheduler background scheduler for daily scans + emails."""
    global _scheduler
    if cfg is None:
        cfg = get_config()

    _scheduler = BackgroundScheduler()

    # Scan every day at the configured time (default 5:30 AM)
    _scheduler.add_job(
        run_scheduled_scan,
        "cron",
        hour=cfg.scheduler.scan_hour,
        minute=cfg.scheduler.scan_minute,
        id="daily_scan",
        replace_existing=True,
    )

    # Send email every day at the configured time (default 6:00 AM)
    _scheduler.add_job(
        run_scheduled_email,
        "cron",
        hour=cfg.scheduler.email_hour,
        minute=cfg.scheduler.email_minute,
        id="daily_email",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started — scan at %02d:%02d, email at %02d:%02d daily",
        cfg.scheduler.scan_hour,
        cfg.scheduler.scan_minute,
        cfg.scheduler.email_hour,
        cfg.scheduler.email_minute,
    )
    return _scheduler


def stop_scheduler() -> None:
    """Shut down the scheduler if it is running."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")
