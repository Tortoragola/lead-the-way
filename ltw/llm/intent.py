"""Real intent enrichment via Gemini + Google Search Grounding.

Grounding and ``response_schema`` cannot be combined in google-genai, so we
ask Gemini for JSON in the prompt and parse it manually, while harvesting
``grounding_metadata`` for the source URLs.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from google import genai
from google.genai import types

from ..config import PRODUCT_DESCRIPTION
from ..models import CompanyIntentProfile, IntentLevel
from .client import MODEL_GROUNDING


def _build_intent_prompt(company_name: str, website: str, country: str) -> str:
    return f"""You are a B2B sales intelligence analyst.

Our product: {PRODUCT_DESCRIPTION}

Task: Using Google Search, find real signals from the **last 90 days** that indicate **purchase intent**
toward our product for the company below.

Company details:
- Name   : {company_name}
- Website: {website or '—'}
- Country: {country or '—'}

Score matrix (mandatory):
- 1-4  → general news, no specific signal found
- 5-7  → hiring activity, team growth, new office / market expansion
- 8-10 → funding round, major technology migration, acquisition, C-level hire

Respond with **ONLY** the JSON below — no extra text, no markdown code fences:

{{
  "intent_score": <integer 1-10>,
  "intent_signals": [
    "Signal 1 — one sentence",
    "Signal 2 — one sentence"
  ]
}}

If no signals are found, return an empty list and score 1-2. Never fabricate — base everything
only on real news or announcements you actually find.
"""


def _strip_code_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return raw


def _extract_json_obj(raw: str) -> dict:
    """Best-effort JSON extraction from a Gemini grounded response."""
    raw = _strip_code_fence(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _extract_grounding_urls(response) -> list[str]:
    urls: list[str] = []
    try:
        candidate = response.candidates[0]
        meta = getattr(candidate, "grounding_metadata", None)
        chunks = getattr(meta, "grounding_chunks", None) or []
        for ch in chunks:
            web = getattr(ch, "web", None)
            uri = getattr(web, "uri", None) if web else None
            if uri and uri not in urls:
                urls.append(uri)
    except (AttributeError, IndexError):
        pass
    return urls


def enrich_intent(
    client: genai.Client,
    unique_id: str,
    company_name: str,
    website: str = "",
    country: str = "",
) -> CompanyIntentProfile:
    """Ground a company against Google Search and return a scored intent profile."""
    import logging
    logger = logging.getLogger(__name__)

    prompt = _build_intent_prompt(company_name, website, country)

    response = client.models.generate_content(
        model=MODEL_GROUNDING,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )

    raw = response.text or ""
    try:
        data = _extract_json_obj(raw)
    except (json.JSONDecodeError, ValueError, Exception) as exc:
        logger.warning("enrich_intent: JSON parse failed for %s — %s", company_name, exc)
        return CompanyIntentProfile(
            unique_id=unique_id,
            company_name=company_name,
            intent_score=1,
            intent_level=IntentLevel.LOW,
            intent_signals=[],
            grounding_urls=[],
            grounding_available=False,
            last_intent_update=datetime.utcnow(),
        )

    score = int(data.get("intent_score", 2))
    score = max(1, min(10, score))
    signals = [str(s) for s in data.get("intent_signals", []) if str(s).strip()]
    grounding_urls = _extract_grounding_urls(response)

    # If no grounding chunks were returned (free-tier or API limitation),
    # cap the score at 4 to avoid false high-confidence signals.
    grounding_available = bool(grounding_urls)
    if not grounding_available:
        score = min(score, 4)
        logger.warning(
            "enrich_intent: no grounding chunks for %s — score capped at %d",
            company_name,
            score,
        )

    return CompanyIntentProfile(
        unique_id=unique_id,
        company_name=company_name,
        intent_score=score,
        intent_level=CompanyIntentProfile.level_from_score(score),
        intent_signals=signals,
        grounding_urls=grounding_urls,
        grounding_available=grounding_available,
        last_intent_update=datetime.utcnow(),
    )
