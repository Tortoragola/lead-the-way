"""Extended guardrails pipeline for user queries.

Layers (in order — fast-to-slow):
  1. Ban-substrings scanner  — blocks known-harmful content markers.
  2. Prompt-injection scanner — existing regex heuristics from ltw/security.py.
  3. (Optional) LLM Guard    — if ``llm-guard`` is installed, runs the
     PromptInjectionV2 scanner from Protect AI for higher recall.
     Install with: pip install llm-guard

Usage:
    from ltw.security.guardrails import run_guardrails
    result = run_guardrails(user_text)
    if not result.safe:
        st.error(result.reason)
        st.stop()
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import check_prompt_injection  # from ltw/security/__init__.py

logger = logging.getLogger(__name__)


# ── Ban-substrings (always applied) ──────────────────────────────────────────
# Normalised to lowercase for matching. Add entries here without regex syntax.
_BANNED_SUBSTRINGS: list[str] = [
    # Exfiltration / data-leaking attempts
    "send all emails to",
    "forward all contacts to",
    "export database to",
    "dump all records",
    # Role-override triggers
    "you are now in developer mode",
    "disregard your instructions",
    "bypass all filters",
    "override your safety",
    # Harmful content
    "how to hack",
    "create malware",
    "write a virus",
    # Extreme jailbreak phrases
    "jailbreak mode",
    "dan mode",
    "evil mode",
]


@dataclass(frozen=True)
class GuardrailsResult:
    safe: bool
    reason: str | None = None
    layers_triggered: list[str] = field(default_factory=list)


def _ban_substrings(text: str) -> GuardrailsResult | None:
    """Return a failed result if any banned substring is found."""
    lower = text.lower()
    for phrase in _BANNED_SUBSTRINGS:
        if phrase in lower:
            return GuardrailsResult(
                safe=False,
                reason=f"Yasaklı içerik tespit edildi: '{phrase}'",
                layers_triggered=["ban_substrings"],
            )
    return None


def _llm_guard_scan(text: str) -> GuardrailsResult | None:
    """Optional LLM Guard PromptInjectionV2 scanner.

    Returns None (pass) when llm-guard is not installed or the scan passes.
    Returns a failed GuardrailsResult if a prompt-injection attack is detected.
    """
    try:
        from llm_guard.input_scanners import PromptInjection  # type: ignore[import]
        from llm_guard.input_scanners.prompt_injection import (  # type: ignore[import]
            MatchType,
        )
    except ImportError:
        return None  # llm-guard not installed — skip silently

    try:
        scanner = PromptInjection(threshold=0.75, match_type=MatchType.FULL)
        sanitized, is_valid, risk_score = scanner.scan(text)
        if not is_valid:
            return GuardrailsResult(
                safe=False,
                reason=f"LLM Guard: prompt injection detected (risk score {risk_score:.2f})",
                layers_triggered=["llm_guard"],
            )
    except Exception as exc:
        logger.warning("LLM Guard scan error (skipped): %s", exc)

    return None


def run_guardrails(text: str) -> GuardrailsResult:
    """Run all guardrail layers against user-supplied text.

    Fast layers run first; the optional ML layer (LLM Guard) runs last.
    Returns a GuardrailsResult with ``safe=True`` if all layers pass.
    """
    # Layer 1: ban-substrings (< 0.1 ms)
    result = _ban_substrings(text)
    if result is not None:
        return result

    # Layer 2: regex prompt-injection patterns from ltw/security.py (< 1 ms)
    basic = check_prompt_injection(text)
    if not basic.safe:
        return GuardrailsResult(
            safe=False,
            reason=basic.reason,
            layers_triggered=["regex_injection"],
        )

    # Layer 3: LLM Guard (optional ML model — ~50-200 ms if installed)
    result = _llm_guard_scan(text)
    if result is not None:
        return result

    return GuardrailsResult(safe=True)
