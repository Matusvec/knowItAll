"""Tech tool model for tracking AI tools, frameworks, and API releases."""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field


class HypeLevel(str, enum.Enum):
    """Assessment of whether a tool is hype or a genuine shift."""

    PURE_HYPE = "pure_hype"
    INCREMENTAL = "incremental"
    GENUINE_SHIFT = "genuine_shift"
    GAME_CHANGER = "game_changer"


class TechTool(BaseModel):
    """A new AI tool, framework, model release, or API."""

    id: str
    name: str
    category: str = ""  # e.g. "framework", "model", "api", "infra"
    released: datetime | None = None

    # Links
    url: str = ""
    docs_url: str = ""
    demo_url: str = ""

    # Analysis
    description: str = ""
    what_it_replaces: str = ""
    who_should_care: str = ""
    hype_level: HypeLevel = HypeLevel.INCREMENTAL
    hype_rationale: str = ""
    use_cases: list[str] = Field(default_factory=list)

    # Scoring
    leverage_score: float = Field(default=0.0, ge=0.0, le=1.0)

    def is_signal(self) -> bool:
        """Return True if this tool represents a genuine leverage shift."""
        return self.hype_level in (HypeLevel.GENUINE_SHIFT, HypeLevel.GAME_CHANGER)
