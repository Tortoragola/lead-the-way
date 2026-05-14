"""DataFrame loading and inspection helpers."""
from __future__ import annotations

import pandas as pd

from .config import DEFAULT_CSV_PATH


def load_default_csv() -> pd.DataFrame:
    return pd.read_csv(DEFAULT_CSV_PATH, low_memory=False)


def load_from_supabase() -> pd.DataFrame:
    """Load people + denormalized company data from Supabase as a DataFrame.

    Returns a DataFrame with the same column names as the original CSV so
    all existing Tab-1 filter and outreach logic works without modification.
    """
    from .db import get_supabase_client

    client = get_supabase_client()

    # Fetch all people rows (Supabase default page size is 1000; use range for safety)
    all_rows: list[dict] = []
    page_size = 1000
    offset = 0
    while True:
        response = (
            client.table("people")
            .select(
                "first_name, last_name, title, email, phone, seniority, "
                "department, sub_department, industry, city, state, country, "
                "linkedin_url, company_name, company_city, company_state, "
                "company_country, company_phone, company_address, "
                "company_linkedin_url, facebook_url, twitter_url, "
                "employees, annual_revenue, technologies, keywords, "
                "target_companies(website, employees_total, sales_volume_dollars)"
            )
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = response.data or []
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    if not all_rows:
        return pd.DataFrame()

    records = []
    for r in all_rows:
        tc = r.pop("target_companies") or {}
        # Map Supabase snake_case columns → CSV-compatible names
        records.append({
            "First Name":           r.get("first_name", ""),
            "Last Name":            r.get("last_name", ""),
            "Title":                r.get("title", ""),
            "Company Name":         r.get("company_name", ""),
            "Company Name for Emails": r.get("company_name", ""),
            "Email":                r.get("email", ""),
            "Seniority":            r.get("seniority", ""),
            "Departments":          r.get("department", ""),
            "Sub Departments":      r.get("sub_department", ""),
            "Corporate Phone":      r.get("phone", ""),
            "# Employees":          tc.get("employees_total") or r.get("employees", ""),
            "Industry":             r.get("industry", ""),
            "Keywords":             _join_json(r.get("keywords")),
            "Person Linkedin Url":  r.get("linkedin_url", ""),
            "Website":              tc.get("website", ""),
            "Company Linkedin Url": r.get("company_linkedin_url", ""),
            "Facebook Url":         r.get("facebook_url", ""),
            "Twitter Url":          r.get("twitter_url", ""),
            "City":                 r.get("city", ""),
            "State":                r.get("state", ""),
            "Country":              r.get("country", ""),
            "Company Address":      r.get("company_address", ""),
            "Company City":         r.get("company_city", ""),
            "Company State":        r.get("company_state", ""),
            "Company Country":      r.get("company_country", ""),
            "Company Phone":        r.get("company_phone", ""),
            "Technologies":         _join_json(r.get("technologies")),
            "Annual Revenue":       tc.get("sales_volume_dollars") or r.get("annual_revenue", ""),
        })

    return pd.DataFrame(records)


def _join_json(value) -> str:
    """Convert a JSONB list (or comma string) back to a comma-separated string."""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value) if value else ""


def sample_values(df: pd.DataFrame, col: str, n: int = 5) -> str:
    vals = df[col].dropna().astype(str)
    vals = vals[vals.str.strip() != ""]
    sample = vals.head(n).tolist()
    ex = " | ".join(sample)
    return ex[:150] + "…" if len(ex) > 150 else ex

