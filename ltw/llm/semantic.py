"""Pre-defined, parameterized SQL query functions exposed as Gemini tools.

LLM never composes SQL strings. All queries use SQLAlchemy bound parameters.
The agent role (ltw_agent) is read-only: SELECT only, no INSERT/UPDATE/DELETE.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy import text

from ..db import get_engine_ro
from ..models import IntentLevel


# ── Result types ─────────────────────────────────────────────────────────────

@dataclass
class CompanyRow:
    unique_id: str
    company_name: str
    country: str | None
    city: str | None
    primary_activity: str | None
    employees_total: int | None
    sales_volume_dollars: float | None
    intent_score: int | None
    intent_level: str | None
    website: str | None


@dataclass
class PersonRow:
    person_id: int
    unique_id: str | None
    first_name: str | None
    last_name: str | None
    title: str | None
    email: str | None
    seniority: str | None
    department: str | None
    industry: str | None
    city: str | None
    country: str | None
    company_name: str | None


@dataclass
class SemanticResult:
    rows: list
    total: int
    truncated: bool = False
    warning: str = ""


# ── Query functions ──────────────────────────────────────────────────────────

def get_companies_by_sector(
    sector: str,
    country: str | None = None,
    intent_level: str | None = None,
    limit: int = 50,
) -> SemanticResult:
    """Filter target_companies by sector keyword + optional country and intent level.

    Searches both ``primary_activity`` and ``keywords`` columns so that short
    user terms like "fintech" match DB values like "Financial Technology Services".
    Results from both columns are UNION-deduped and ordered by intent_score.
    """
    limit = min(limit, 200)

    params: dict = {"sector": f"%{sector}%", "limit": limit}
    extra = []

    if country:
        extra.append("LOWER(country) = LOWER(:country)")
        params["country"] = country
    if intent_level:
        extra.append("intent_level = :intent_level")
        params["intent_level"] = intent_level

    extra_clause = ("AND " + " AND ".join(extra)) if extra else ""

    sql = text(f"""
        SELECT DISTINCT ON (unique_id)
               unique_id, company_name, country, city, primary_activity,
               employees_total, sales_volume_dollars, intent_score, intent_level, website
        FROM target_companies
        WHERE (
            LOWER(primary_activity) LIKE LOWER(:sector)
            OR LOWER(COALESCE(keywords::text, '')) LIKE LOWER(:sector)
        )
        {extra_clause}
        ORDER BY unique_id, intent_score DESC NULLS LAST
        LIMIT :limit
    """)

    with get_engine_ro().connect() as conn:
        result = conn.execute(sql, params)
        rows = [CompanyRow(**dict(r._mapping)) for r in result]

    return SemanticResult(rows=rows, total=len(rows))


def get_high_intent_leads(
    min_score: int = 8,
    country: str | None = None,
    limit: int = 20,
) -> SemanticResult:
    """Return companies with intent_score >= min_score, ordered by score descending."""
    limit = min(limit, 100)
    params: dict = {"min_score": max(1, min(10, min_score)), "limit": limit}
    where = ["intent_score >= :min_score"]

    if country:
        where.append("LOWER(country) = LOWER(:country)")
        params["country"] = country

    sql = text(f"""
        SELECT unique_id, company_name, country, city, primary_activity,
               employees_total, sales_volume_dollars, intent_score, intent_level, website
        FROM target_companies
        WHERE {' AND '.join(where)}
        ORDER BY intent_score DESC
        LIMIT :limit
    """)

    with get_engine_ro().connect() as conn:
        result = conn.execute(sql, params)
        rows = [CompanyRow(**dict(r._mapping)) for r in result]

    return SemanticResult(rows=rows, total=len(rows))


def get_contacts_for_company(
    unique_id: str,
    seniority: str | None = None,
) -> SemanticResult:
    """Return people rows linked to the given company unique_id."""
    params: dict = {"unique_id": unique_id}
    where = ["p.unique_id = :unique_id", "p.opt_out = FALSE"]

    if seniority:
        where.append("LOWER(p.seniority) = LOWER(:seniority)")
        params["seniority"] = seniority

    sql = text(f"""
        SELECT p.person_id, p.unique_id, p.first_name, p.last_name, p.title,
               p.email, p.seniority, p.department, p.industry,
               p.city, p.country, p.company_name
        FROM people p
        WHERE {' AND '.join(where)}
        LIMIT 50
    """)

    with get_engine_ro().connect() as conn:
        result = conn.execute(sql, params)
        rows = [PersonRow(**dict(r._mapping)) for r in result]

    return SemanticResult(rows=rows, total=len(rows))


def search_companies(query: str, limit: int = 30) -> SemanticResult:
    """Full-text ILIKE search on company_name. LLM never composes SQL strings."""
    limit = min(limit, 100)
    sql = text("""
        SELECT unique_id, company_name, country, city, primary_activity,
               employees_total, sales_volume_dollars, intent_score, intent_level, website
        FROM target_companies
        WHERE company_name ILIKE :q
        ORDER BY intent_score DESC NULLS LAST
        LIMIT :limit
    """)
    with get_engine_ro().connect() as conn:
        result = conn.execute(sql, {"q": f"%{query}%", "limit": limit})
        rows = [CompanyRow(**dict(r._mapping)) for r in result]

    return SemanticResult(rows=rows, total=len(rows))


def search_people(
    title: str | None = None,
    seniority: str | None = None,
    department: str | None = None,
    country: str | None = None,
    industry: str | None = None,
    limit: int = 50,
) -> SemanticResult:
    """Search contacts by title / seniority / department / country / industry.

    All filters are optional and combined with AND logic. Title, department,
    and industry use ILIKE for partial matching. Seniority and country use
    case-insensitive equality. Call multiple times with different terms to
    cover synonyms, then deduplicate by email.
    """
    limit = min(limit, 200)
    params: dict = {"limit": limit}
    where = ["p.opt_out = FALSE"]

    if title:
        where.append("p.title ILIKE :title")
        params["title"] = f"%{title}%"
    if seniority:
        where.append("LOWER(p.seniority) = LOWER(:seniority)")
        params["seniority"] = seniority
    if department:
        where.append("p.department ILIKE :department")
        params["department"] = f"%{department}%"
    if country:
        where.append("LOWER(p.country) = LOWER(:country)")
        params["country"] = country
    if industry:
        where.append("p.industry ILIKE :industry")
        params["industry"] = f"%{industry}%"

    sql = text(f"""
        SELECT p.person_id, p.unique_id, p.first_name, p.last_name, p.title,
               p.email, p.seniority, p.department, p.industry,
               p.city, p.country, p.company_name
        FROM people p
        WHERE {' AND '.join(where)}
        ORDER BY p.seniority, p.title
        LIMIT :limit
    """)

    with get_engine_ro().connect() as conn:
        result = conn.execute(sql, params)
        rows = [PersonRow(**dict(r._mapping)) for r in result]

    return SemanticResult(rows=rows, total=len(rows))


def count_leads(
    title: str | None = None,
    seniority: str | None = None,
    department: str | None = None,
    country: str | None = None,
    industry: str | None = None,
) -> SemanticResult:
    """Count matching contacts without fetching rows.

    Use this before a broad search to gauge result volume. Returns a
    SemanticResult with one element: {"count": <int>}.
    """
    params: dict = {}
    where = ["p.opt_out = FALSE"]

    if title:
        where.append("p.title ILIKE :title")
        params["title"] = f"%{title}%"
    if seniority:
        where.append("LOWER(p.seniority) = LOWER(:seniority)")
        params["seniority"] = seniority
    if department:
        where.append("p.department ILIKE :department")
        params["department"] = f"%{department}%"
    if country:
        where.append("LOWER(p.country) = LOWER(:country)")
        params["country"] = country
    if industry:
        where.append("p.industry ILIKE :industry")
        params["industry"] = f"%{industry}%"

    sql = text(f"""
        SELECT COUNT(*) AS count
        FROM people p
        WHERE {' AND '.join(where)}
    """)

    with get_engine_ro().connect() as conn:
        row = conn.execute(sql, params).fetchone()
        count = int(row[0]) if row else 0

    return SemanticResult(rows=[{"count": count}], total=count)


def get_company_details(unique_id: str) -> SemanticResult:
    """Return the full profile of a single company by its unique_id."""
    sql = text("""
        SELECT unique_id, company_name, country, city, primary_activity,
               employees_total, sales_volume_dollars, intent_score, intent_level, website
        FROM target_companies
        WHERE unique_id = :uid
        LIMIT 1
    """)
    with get_engine_ro().connect() as conn:
        result = conn.execute(sql, {"uid": unique_id})
        rows = [CompanyRow(**dict(r._mapping)) for r in result]

    return SemanticResult(rows=rows, total=len(rows))


# Columns the LLM is allowed to inspect with get_distinct_values.
# This allowlist is the security boundary — column name is f-stringed.
_DISTINCT_COLUMN_ALLOWLIST: frozenset[str] = frozenset(
    {"country", "industry", "seniority", "department", "city"}
)


def get_distinct_values(column: str) -> SemanticResult:
    """Return distinct non-null values for a people-table column.

    Allowed columns: country, industry, seniority, department, city.
    Use this to discover valid filter values before calling search_people.
    """
    if column not in _DISTINCT_COLUMN_ALLOWLIST:
        raise ValueError(
            f"Column '{column}' is not allowed. "
            f"Choose one of: {sorted(_DISTINCT_COLUMN_ALLOWLIST)}"
        )

    sql = text(f"""
        SELECT DISTINCT {column} AS val
        FROM people
        WHERE opt_out = FALSE AND {column} IS NOT NULL
        ORDER BY {column}
        LIMIT 100
    """)

    with get_engine_ro().connect() as conn:
        result = conn.execute(sql)
        values = [row[0] for row in result if row[0]]

    return SemanticResult(rows=[{"values": values}], total=len(values))
