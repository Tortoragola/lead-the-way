"""Pydantic models used across LLM calls and persistence."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class FilterRule(BaseModel):
    column: str
    operator: str
    value: str


class FilterRequest(BaseModel):
    filters: list[FilterRule] = Field(default_factory=list)
    logic: str = "AND"


class OutreachResult(BaseModel):
    """Structured output for the outreach generator."""

    intent: str = Field(description="One-sentence purchase intent statement.")
    email_draft: str = Field(
        description="Cold sales email starting with 'Subject:', 3-4 paragraphs in English."
    )


# ── Intent layer ─────────────────────────────────────────────────────────────

class IntentLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


SignalCategory = Literal["news", "hiring", "funding", "tech", "expansion"]


class IntentSignal(BaseModel):
    text: str = Field(description="Short description of the signal (one sentence).")
    category: SignalCategory
    weight: int = Field(ge=1, le=10, description="Signal weight contribution to the intent score (1-10).")


class CompanyIntentProfile(BaseModel):
    """Real, grounded intent profile for a company."""

    unique_id: str = Field(description="Unique company identifier or normalized name.")
    company_name: str
    intent_score: int = Field(ge=1, le=10, description="Purchase intent score from 1 to 10.")
    intent_level: IntentLevel
    intent_signals: list[str] = Field(
        default_factory=list,
        description="Detected intent signals as short one-sentence strings.",
    )
    grounding_urls: list[str] = Field(
        default_factory=list,
        description="Source URLs backing the intent signals.",
    )
    grounding_available: bool = Field(
        default=True,
        description="False if Google Search Grounding returned no chunks (e.g. free-tier limitation).",
    )
    last_intent_update: datetime = Field(default_factory=datetime.utcnow)

    @staticmethod
    def level_from_score(score: int) -> IntentLevel:
        if score >= 8:
            return IntentLevel.HIGH
        if score >= 5:
            return IntentLevel.MEDIUM
        return IntentLevel.LOW
