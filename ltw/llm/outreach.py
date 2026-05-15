"""Outreach intent + email generation with Pydantic-validated output."""
from __future__ import annotations

import json

from google import genai
from google.genai import types

from ..models import CompanyIntentProfile, OutreachResult
from .client import MODEL_EXTRACTION, MODEL_REASONING
from .prompts import build_outreach_prompt


def generate_outreach(
    client: genai.Client,
    person: dict,
    intent_profile: CompanyIntentProfile | None = None,
) -> OutreachResult:
    """Generate (intent, email_draft) for a single contact, validated by Pydantic.

    Uses MODEL_EXTRACTION (Lite) when intent_profile is already provided — email
    generation is mostly templating in that case, so Flash is overkill.
    Uses MODEL_REASONING (Flash) when the model must invent the intent hook from scratch.
    """
    prompt = build_outreach_prompt(person, intent_profile)
    # Use Lite when intent signals are already known; Flash when reasoning from scratch.
    model = MODEL_EXTRACTION if intent_profile is not None else MODEL_REASONING

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=OutreachResult,
        ),
    )

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, OutreachResult):
        return parsed

    raw = (response.text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    data = json.loads(raw)
    return OutreachResult.model_validate(data)
