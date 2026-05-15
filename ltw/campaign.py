"""Campaign management for batch email draft generation."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import csv
from io import StringIO
import uuid


@dataclass
class OutreachDraft:
    """Single generated email draft."""
    first_name: str
    last_name: str
    email: str
    company_name: str
    subject: str
    body: str
    intent_score: int
    industry: str = ""


@dataclass
class Campaign:
    """Campaign container for batch email draft generation and scheduling."""
    name: str
    query: str  # Natural language query, e.g., "İstanbul'da fintech VP'ler"
    min_intent_score: int = 5
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "draft"  # draft, ready, executing, completed
    scheduled_at: Optional[str] = None  # "daily 09:00", "weekly Monday", None for manual
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    drafts: list[OutreachDraft] = field(default_factory=list)

    def save_draft(self, draft: OutreachDraft) -> None:
        """Add drafted email to campaign."""
        self.drafts.append(draft)
        self.updated_at = datetime.utcnow()

    def save_drafts(self, drafts: list[OutreachDraft]) -> None:
        """Add multiple drafts to campaign."""
        self.drafts.extend(drafts)
        self.updated_at = datetime.utcnow()

    def get_draft_count(self) -> int:
        """Get number of drafts in campaign."""
        return len(self.drafts)

    def to_dict(self) -> dict:
        """Convert to dictionary for Supabase storage."""
        return {
            "id": self.id,
            "name": self.name,
            "query": self.query,
            "min_intent_score": self.min_intent_score,
            "status": self.status,
            "scheduled_at": self.scheduled_at,
            "draft_count": self.get_draft_count(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "results_json": {
                "drafts": [
                    {
                        "first_name": d.first_name,
                        "last_name": d.last_name,
                        "email": d.email,
                        "company_name": d.company_name,
                        "subject": d.subject,
                        "body": d.body,
                        "intent_score": d.intent_score,
                        "industry": d.industry,
                    }
                    for d in self.drafts
                ]
            },
        }

    def to_csv(self) -> str:
        """Export drafts as CSV string."""
        output = StringIO()
        if not self.drafts:
            return ""

        fieldnames = [
            "first_name",
            "last_name",
            "email",
            "company_name",
            "subject",
            "body",
            "intent_score",
            "industry",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for draft in self.drafts:
            writer.writerow(
                {
                    "first_name": draft.first_name,
                    "last_name": draft.last_name,
                    "email": draft.email,
                    "company_name": draft.company_name,
                    "subject": draft.subject,
                    "body": draft.body,
                    "intent_score": draft.intent_score,
                    "industry": draft.industry,
                }
            )

        return output.getvalue()

    @staticmethod
    def from_dict(data: dict) -> Campaign:
        """Create Campaign from Supabase record."""
        drafts = []
        if data.get("results_json") and "drafts" in data["results_json"]:
            for d in data["results_json"]["drafts"]:
                drafts.append(
                    OutreachDraft(
                        first_name=d.get("first_name", ""),
                        last_name=d.get("last_name", ""),
                        email=d.get("email", ""),
                        company_name=d.get("company_name", ""),
                        subject=d.get("subject", ""),
                        body=d.get("body", ""),
                        intent_score=d.get("intent_score", 0),
                        industry=d.get("industry", ""),
                    )
                )

        return Campaign(
            id=data.get("id"),
            name=data.get("name", ""),
            query=data.get("query", ""),
            min_intent_score=data.get("min_intent_score", 5),
            status=data.get("status", "draft"),
            scheduled_at=data.get("scheduled_at"),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else datetime.utcnow(),
            drafts=drafts,
        )
