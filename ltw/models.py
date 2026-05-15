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

    intent: str = Field(description="Tek cümlelik sentetik satın alma niyeti.")
    email_draft: str = Field(
        description="Subject: ile başlayan, 3-4 paragraflık İngilizce soğuk satış maili."
    )


# ── Intent layer ─────────────────────────────────────────────────────────────

class IntentLevel(str, Enum):
    HIGH = "YÜKSEK"
    MEDIUM = "ORTA"
    LOW = "DÜŞÜK"


SignalCategory = Literal["news", "hiring", "funding", "tech", "expansion"]


class IntentSignal(BaseModel):
    text: str = Field(description="Sinyalin kısa açıklaması (tek cümle).")
    category: SignalCategory
    weight: int = Field(ge=1, le=10, description="Sinyalin niyet skoruna katkı ağırlığı (1-10).")


class CompanyIntentProfile(BaseModel):
    """Real, grounded intent profile for a company."""

    unique_id: str = Field(description="Şirketin benzersiz kimliği veya normalize edilmiş adı.")
    company_name: str
    intent_score: int = Field(ge=1, le=10, description="1-10 arası satın alma niyeti skoru.")
    intent_level: IntentLevel
    intent_signals: list[str] = Field(
        default_factory=list,
        description="Kısa cümleler halinde tespit edilen niyet sinyalleri.",
    )
    grounding_urls: list[str] = Field(
        default_factory=list,
        description="Sinyallerin dayandığı kaynak URL'leri.",
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
