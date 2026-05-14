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
from .client import MODEL_REASONING


def _build_intent_prompt(company_name: str, website: str, country: str) -> str:
    return f"""Sen bir B2B satış istihbarat analistisin.

Ürünümüz: {PRODUCT_DESCRIPTION}

Görev: Aşağıdaki şirket için **son 90 gün** içindeki, ürünümüze yönelik **satın alma niyetine** işaret eden gerçek sinyalleri Google ile araştır.

Şirket bilgileri:
- Ad: {company_name}
- Web sitesi: {website or '—'}
- Ülke: {country or '—'}

Skor matrisi (zorunlu):
- 1-4 → genel haberler, özgün bir sinyal yok
- 5-7 → işe alım, ekip büyütme, yeni ofis/pazar genişlemesi
- 8-10 → yatırım turu, büyük teknoloji geçişi, satın alma, üst düzey atama

Yanıtını **YALNIZCA** aşağıdaki JSON formatında ver, başka hiçbir şey ekleme,
markdown kod bloğu kullanma:

{{
  "intent_score": <1-10 arası tam sayı>,
  "intent_signals": [
    "Sinyal 1 - tek cümle",
    "Sinyal 2 - tek cümle"
  ]
}}

Sinyal bulamazsan boş liste döndür ve 1-2 skor ver. Asla uydurma; sadece
gerçekten bulduğun haber/duyurulara dayan.
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
    prompt = _build_intent_prompt(company_name, website, country)

    response = client.models.generate_content(
        model=MODEL_REASONING,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )

    raw = response.text or ""
    try:
        data = _extract_json_obj(raw)
    except (json.JSONDecodeError, ValueError):
        data = {"intent_score": 2, "intent_signals": []}

    score = int(data.get("intent_score", 2))
    score = max(1, min(10, score))
    signals = [str(s) for s in data.get("intent_signals", []) if str(s).strip()]
    grounding_urls = _extract_grounding_urls(response)

    return CompanyIntentProfile(
        unique_id=unique_id,
        company_name=company_name,
        intent_score=score,
        intent_level=CompanyIntentProfile.level_from_score(score),
        intent_signals=signals,
        grounding_urls=grounding_urls,
        last_intent_update=datetime.utcnow(),
    )
