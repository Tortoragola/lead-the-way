"""Gemini client factory and model constants.

Free-tier routing:
- LITE      → function-call argument extraction (filter parsing, mid-chain arg-fill).
- FLASH     → reasoning, outreach writing, orchestration.
- GROUNDING → Google Search Grounding calls (Gemini 2/2.5 only; Gemini 3 does not
              support grounding as of May 2026).
- Pro is unavailable on the free tier; do NOT add a PRO constant here.
"""
from __future__ import annotations

from functools import lru_cache

from google import genai


# Models confirmed via ListModels (May 2026).
# gemini-3-flash-preview — frontier-class reasoning, best available flash.
# gemini-3.1-flash-lite  — stable Gemini 3 lite, best for fast extraction.
# gemini-2.5-flash      — last model generation with Search Grounding support.
MODEL_LITE = "gemini-3.1-flash-lite"
MODEL_FLASH = "gemini-3-flash-preview"
MODEL_GROUNDING = "gemini-2.5-flash"  # Gemini 2/2.5 only support grounding

# Semantic aliases used at call sites.
MODEL_EXTRACTION = MODEL_LITE
MODEL_REASONING = MODEL_FLASH


@lru_cache(maxsize=4)
def get_client(api_key: str) -> genai.Client:
    """Return a cached Gemini client for the given API key."""
    return genai.Client(api_key=api_key)
