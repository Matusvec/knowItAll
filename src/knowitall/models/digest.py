"""Digest models for the interactive daily intelligence report."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from knowitall.models.paper import Paper
from knowitall.models.startup_idea import StartupIdea
from knowitall.models.tool import TechTool
from knowitall.models.opportunity import Opportunity


class ActionItem(BaseModel):
    """A follow-up action attached to a digest item."""

    label: str  # e.g. "Generate an MVP plan"
    action_type: str  # e.g. "mvp_plan", "competition_assessment", "cost_estimate"
    target_id: str  # ID of the related item
    description: str = ""


class DigestSection(BaseModel):
    """A named section within the daily digest."""

    title: str
    items_count: int = 0
    summary: str = ""


class DailyDigest(BaseModel):
    """The complete daily intelligence digest, interactive and skimmable."""

    date: date
    headline: str = ""

    papers: list[Paper] = Field(default_factory=list)
    startup_ideas: list[StartupIdea] = Field(default_factory=list)
    tools: list[TechTool] = Field(default_factory=list)
    opportunities: list[Opportunity] = Field(default_factory=list)
    actions: list[ActionItem] = Field(default_factory=list)

    sections: list[DigestSection] = Field(default_factory=list)

    def build_sections(self) -> None:
        """Populate section metadata from the digest contents."""
        self.sections = []
        if self.papers:
            self.sections.append(
                DigestSection(
                    title="Research Signals",
                    items_count=len(self.papers),
                    summary=f"{len(self.papers)} papers worth your attention today.",
                )
            )
        if self.startup_ideas:
            self.sections.append(
                DigestSection(
                    title="Startup Ideas",
                    items_count=len(self.startup_ideas),
                    summary=f"{len(self.startup_ideas)} actionable ideas from today's signals.",
                )
            )
        if self.tools:
            self.sections.append(
                DigestSection(
                    title="Tech & Tools",
                    items_count=len(self.tools),
                    summary=f"{len(self.tools)} new tools or releases to evaluate.",
                )
            )
        if self.opportunities:
            self.sections.append(
                DigestSection(
                    title="Opportunity Radar",
                    items_count=len(self.opportunities),
                    summary=f"{len(self.opportunities)} opportunities on your radar.",
                )
            )

    def total_signals(self) -> int:
        """Return the total number of signals in this digest."""
        return (
            len(self.papers)
            + len(self.startup_ideas)
            + len(self.tools)
            + len(self.opportunities)
        )
