"""Test whether Google Search Grounding works with the current API key.

Usage:
    python -m scripts.test_grounding

Exit codes:
    0  Grounding is available (grounding_chunks returned).
    1  Grounding is NOT available (no chunks — likely a free-tier limitation).
    2  API call failed entirely.

Useful for diagnosing intent enrichment reliability before a demo.
"""
from __future__ import annotations

import logging
import sys

from google.genai import types

from ltw.config import get_settings
from ltw.llm.client import MODEL_REASONING, get_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TEST_COMPANY = "Microsoft"
TEST_PROMPT = (
    f"In one sentence, what is the most recent notable news about {TEST_COMPANY}? "
    "Use Google Search to find a real, current result."
)


def main() -> int:
    settings = get_settings()
    client = get_client(settings.gemini_api_key)

    logger.info("Calling %s with Google Search Grounding on '%s'…", MODEL_REASONING, TEST_COMPANY)
    try:
        response = client.models.generate_content(
            model=MODEL_REASONING,
            contents=TEST_PROMPT,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
    except Exception as exc:
        logger.error("API call failed: %s", exc)
        return 2

    # Inspect grounding metadata
    chunks: list = []
    try:
        candidate = response.candidates[0]
        meta = getattr(candidate, "grounding_metadata", None)
        chunks = list(getattr(meta, "grounding_chunks", None) or [])
    except (AttributeError, IndexError):
        pass

    if chunks:
        logger.info("✅ Grounding AVAILABLE — %d chunk(s) returned.", len(chunks))
        for ch in chunks[:3]:
            web = getattr(ch, "web", None)
            uri = getattr(web, "uri", None) if web else None
            title = getattr(web, "title", None) if web else None
            logger.info("  chunk: %s — %s", title, uri)
        return 0
    else:
        logger.warning(
            "❌ Grounding NOT available — no grounding_chunks in response. "
            "Model answer was: %s",
            (response.text or "")[:200],
        )
        logger.warning(
            "This likely means your API key does not have Google Search Grounding "
            "access (free-tier limitation). Intent scores will be capped at 4."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
