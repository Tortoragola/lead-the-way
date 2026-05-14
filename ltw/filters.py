"""DataFrame filtering primitives (UI-independent)."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


OPERATORS = {
    "contains":     lambda s, v: s.astype(str).str.contains(str(v), case=False, na=False),
    "not_contains": lambda s, v: ~s.astype(str).str.contains(str(v), case=False, na=False),
    "equals":       lambda s, v: s.astype(str).str.lower() == str(v).lower(),
    "not_equals":   lambda s, v: s.astype(str).str.lower() != str(v).lower(),
    "starts_with":  lambda s, v: s.astype(str).str.lower().str.startswith(str(v).lower()),
    "ends_with":    lambda s, v: s.astype(str).str.lower().str.endswith(str(v).lower()),
    "greater_than": lambda s, v: pd.to_numeric(s, errors="coerce") > float(v),
    "less_than":    lambda s, v: pd.to_numeric(s, errors="coerce") < float(v),
    "in_list":      lambda s, v: s.astype(str).str.lower().isin(
                        [x.strip().lower() for x in (v.split(",") if isinstance(v, str) else v)]
                    ),
}

# Columns where exact `equals` almost always misses results because values are
# free-text or multi-valued (e.g. "Marketing, Sales" in Departments).
_FUZZY_TEXT_COLS = frozenset({
    "Title", "Departments", "Sub Departments",
    "Industry", "Technologies", "Keywords",
    "Company Name", "Company Name for Emails",
})


@dataclass
class FilterOutcome:
    df: pd.DataFrame
    warnings: list[str] = field(default_factory=list)


def normalize_filters(filters: list[dict]) -> tuple[list[dict], list[str]]:
    """Upgrade Gemini-generated filters to maximise recall.

    Rule: convert ``equals`` → ``contains`` for free-text columns so that
    multi-valued cells like "Marketing, Sales" are not silently skipped.

    Returns (normalized_filters, info_notes).
    """
    notes: list[str] = []
    normalized = []
    for f in filters:
        f = dict(f)
        col = f.get("column", "")
        op  = f.get("operator", "")
        if col in _FUZZY_TEXT_COLS and op == "equals":
            f["operator"] = "contains"
            notes.append(
                f"💡 '{col}' sütununda `equals` → `contains` olarak genişletildi"
                " (birleşik değerler kaçırılmasın diye)."
            )
        normalized.append(f)
    return normalized, notes


def filter_dataframe(
    df: pd.DataFrame,
    filters: list[dict],
    logic: str = "AND",
) -> FilterOutcome:
    """Apply filter rules to ``df``. Returns filtered DataFrame plus warnings."""
    warnings: list[str] = []

    if not filters:
        return FilterOutcome(df=df, warnings=warnings)

    masks = []
    for rule in filters:
        col = rule.get("column", "").strip()
        op = rule.get("operator", "contains").strip()
        val = rule.get("value", "")

        if col not in df.columns:
            warnings.append(f"Sütun bulunamadı: **{col}** — bu kural atlandı.")
            continue
        if op not in OPERATORS:
            warnings.append(f"Bilinmeyen operatör: **{op}** — bu kural atlandı.")
            continue
        try:
            masks.append(OPERATORS[op](df[col], val))
        except Exception as e:
            warnings.append(f"Filtre hatası ({col} {op} {val}): {e}")

    if not masks:
        return FilterOutcome(df=df, warnings=warnings)

    combined = masks[0]
    for m in masks[1:]:
        combined = combined & m if logic.upper() == "AND" else combined | m

    return FilterOutcome(df=df[combined], warnings=warnings)
