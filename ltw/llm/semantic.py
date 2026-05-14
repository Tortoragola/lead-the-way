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
    """Filter target_companies by sector keyword + optional country and intent level."""
    limit = min(limit, 200)

    params: dict = {"sector": f"%{sector}%", "limit": limit}
    where = ["LOWER(primary_activity) LIKE LOWER(:sector)"]

    if country:
        where.append("LOWER(country) = LOWER(:country)")
        params["country"] = country
    if intent_level:
        where.append("intent_level = :intent_level")
        params["intent_level"] = intent_level

    sql = text(f"""
        SELECT unique_id, company_name, country, city, primary_activity,
               employees_total, sales_volume_dollars, intent_score, intent_level, website
        FROM target_companies
        WHERE {' AND '.join(where)}
          AND opt_out IS DISTINCT FROM TRUE
        ORDER BY intent_score DESC NULLS LAST
        LIMIT :limit
    """.replace("opt_out IS DISTINCT FROM TRUE", "TRUE"))  # target_companies has no opt_out

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
