"""Prompt builders kept separate from call sites."""
from __future__ import annotations

import pandas as pd

from ..data import sample_values
from ..config import PRODUCT_DESCRIPTION
from ..models import CompanyIntentProfile


def build_system_prompt(df: pd.DataFrame) -> str:
    col_lines = [f'  "{col}": sample → {sample_values(df, col)}' for col in df.columns]
    return (
        "You are a B2B contact database filtering assistant.\n"
        "Analyse the user's natural-language query and call filter_dataframe.\n"
        "Always translate non-English terms to English before using them as filter values "
        "(e.g. 'pazarlama' → 'marketing', 'müdür' → 'manager').\n\n"
        "FILTER STRATEGY (critical rules):\n"
        "1. For Title, Departments, Industry, Technologies, Keywords ALWAYS use `contains` — never `equals`.\n"
        "   Reason: cells may contain combined values like 'Marketing, Sales'; `equals` would miss them.\n"
        "2. For Country and Seniority use `equals` or `in_list`.\n"
        "3. For title+department combos (e.g. 'marketing manager'):\n"
        "   WRONG: [Title contains 'Manager'] AND [Departments equals 'Marketing']\n"
        "   RIGHT : [Title contains 'Marketing Manager'] — single filter, full expression\n"
        "   OR    : [Title contains 'Marketing Manager'] OR [Departments contains 'Marketing'] — OR logic\n"
        "4. When filtering both Title and Departments, use OR logic — not AND;\n"
        "   because a person whose title is 'Marketing Manager' but whose department is labelled differently \n"
        "   would be lost with AND.\n\n"
        "Available CSV columns and sample values:\n"
        + "\n".join(col_lines)
        + "\n\nRespond to the user in Turkish."
    )


def build_outreach_prompt(
    person: dict,
    intent_profile: CompanyIntentProfile | None = None,
) -> str:
    first    = person.get("First Name", "")
    last     = person.get("Last Name", "")
    title    = person.get("Title", "")
    company  = person.get("Company Name", "")
    industry = person.get("Industry", "")
    city     = person.get("City", "")
    country  = person.get("Country", "")
    email    = person.get("Email", "")
    employees = person.get("# Employees", "")

    if intent_profile and intent_profile.intent_signals:
        signals_block = "\n".join(f"- {s}" for s in intent_profile.intent_signals)
        intent_section = f"""

VERIFIED INTENT SIGNALS (Google-grounded, last 90 days):
Score: {intent_profile.intent_score}/10 ({intent_profile.intent_level.value})
{signals_block}

IMPORTANT: In task 1 (intent), summarise the strongest of these real signals in a single sentence.
Do NOT fabricate or hallucinate signals.
"""
    else:
        intent_section = ""

    return f"""You are an experienced B2B sales expert.

Our product: {PRODUCT_DESCRIPTION}

Target contact:
- Full Name  : {first} {last}
- Title      : {title}
- Company    : {company}
- Industry   : {industry}
- Location   : {city}, {country}
- Employees  : {employees}
- Email      : {email}
{intent_section}
You have two tasks:

1. PURCHASE INTENT (intent):
Write a single realistic, specific, convincing sentence describing why this company might need our product.
Make it sector- and company-specific; avoid generic phrases.

2. COLD EMAIL (email_draft):
Using the intent above, write a persuasive, professional, concise (3-4 paragraph) cold sales email to {first}.
Put the subject line (Subject:) at the top. Use the company name and title naturally. End with "Best regards,\\nLead The Way Team".
"""
