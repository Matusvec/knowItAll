"""Startup idea model generated from research-to-market translation."""

from __future__ import annotations

import enum
from pydantic import BaseModel, Field


class Complexity(str, enum.Enum):
    """Technical complexity level for a startup idea."""

    LOW = "low"
    MEDIUM = "medium"
    HARD = "hard"


class StartupSignal(BaseModel):
    """A market signal that informs a startup idea."""

    description: str
    source: str = ""
    url: str = ""


class StartupIdea(BaseModel):
    """A concrete startup idea derived from research + market signals."""

    id: str
    title: str
    target_user: str = ""
    core_insight: str = ""
    defensibility: str = ""
    complexity: Complexity = Complexity.MEDIUM
    build_timeline: str = ""  # e.g. "2-4 weeks", "3-6 months"
    required_tools: list[str] = Field(default_factory=list)

    # Source signals that generated this idea
    paper_ids: list[str] = Field(default_factory=list)
    market_signals: list[StartupSignal] = Field(default_factory=list)

    # Anti-fluff: explicitly flag what NOT to pursue
    not_worth_pursuing: str = ""
    why_not: str = ""

    # Action items
    mvp_steps: list[str] = Field(default_factory=list)
    competition_notes: str = ""
    estimated_cost: str = ""
    pitch_hook: str = ""

    def is_actionable(self) -> bool:
        """Return True if this idea has enough detail to act on."""
        return bool(
            self.target_user
            and self.core_insight
            and self.build_timeline
            and self.required_tools
        )
