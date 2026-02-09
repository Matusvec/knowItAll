"""Opportunity model for hackathons, accelerators, grants, and competitions."""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field


class OpportunityType(str, enum.Enum):
    """Type of founder opportunity."""

    HACKATHON = "hackathon"
    ACCELERATOR = "accelerator"
    GRANT = "grant"
    COMPETITION = "competition"
    STRATEGIC_TIMING = "strategic_timing"


class Opportunity(BaseModel):
    """A founder-relevant opportunity with ROI assessment."""

    id: str
    title: str
    opportunity_type: OpportunityType
    description: str = ""
    url: str = ""

    # Timing
    deadline: datetime | None = None
    event_date: datetime | None = None

    # ROI assessment
    roi_score: float = Field(default=0.0, ge=0.0, le=1.0)
    resume_value: str = ""
    network_leverage: str = ""
    speed_to_validation: str = ""

    # Strategic context
    timing_note: str = ""  # e.g. "new model makes X suddenly viable"
    action_steps: list[str] = Field(default_factory=list)

    def is_high_priority(self) -> bool:
        """Return True if this opportunity scores above the priority threshold."""
        return self.roi_score >= 0.7
