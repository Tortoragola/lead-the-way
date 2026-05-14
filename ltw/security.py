"""Security & compliance utilities for Lead The Way.

Provides prompt-injection detection for user queries (OWASP LLM01).
The check is a fast regex/heuristic — adds < 1 ms latency, no model downloads.

Note: PII masking is intentionally omitted. Lead The Way's core value is
providing contact data; masking it would break the product.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# ── Prompt-injection patterns (OWASP LLM01 mitigations) ──────────────────────
_INJECTION_PATTERNS = [
    # Classic jailbreak triggers
    re.compile(r"\bignore\s+(all\s+)?previous\s+instructions?\b", re.I),
    re.compile(r"\bforget\s+(all\s+)?previous\s+instructions?\b", re.I),
    re.compile(r"\byou\s+are\s+now\b.{0,40}\b(DAN|jailbreak|unrestricted)\b", re.I),
    re.compile(r"\bact\s+as\s+(if\s+you\s+are\s+)?(a\s+)?(?!an?\s+SDR).{0,30}(no\s+restrictions?|unrestricted)\b", re.I),
    # Instruction override patterns
    re.compile(r"\bsystem\s*prompt\b", re.I),
    re.compile(r"\bpretend\s+(you\s+have\s+)?no\s+(ethical\s+)?guidelines?\b", re.I),
    re.compile(r"\bdo\s+anything\s+now\b", re.I),
    re.compile(r"</?(s|system|instruction|prompt)>", re.I),
    # SQL / shell injection (for queries that end up in DB tool args)
    re.compile(r";\s*(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE)\s+", re.I),
    re.compile(r"--\s*$", re.M),
    re.compile(r"'\s*OR\s+'?\d+'?\s*=\s*'?\d+", re.I),
]


@dataclass(frozen=True)
class GuardResult:
    safe: bool
    reason: str | None = None  # populated when safe=False


def check_prompt_injection(text: str) -> GuardResult:
    """Fast heuristic check for prompt-injection in user-supplied text.

    Returns GuardResult(safe=True) if clean, GuardResult(safe=False, reason=…) if suspicious.
    """
    for pattern in _INJECTION_PATTERNS:
        m = pattern.search(text)
        if m:
            return GuardResult(safe=False, reason=f"Şüpheli girdi tespit edildi: '{m.group()[:60]}'")
    return GuardResult(safe=True)



