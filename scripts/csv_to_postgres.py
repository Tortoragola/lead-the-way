#!/usr/bin/env python
"""ETL: Load Bones CSV files → PostgreSQL.

Usage:
    python scripts/csv_to_postgres.py

Requires DATABASE_URL (writer role) in environment or .env file.
Idempotent: uses INSERT … ON CONFLICT DO UPDATE.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running from the project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv(ROOT / ".env")

FIRMOGRAPHIC_CSV = ROOT / "Bones - Firmographic Data Sample - Sample_Records.csv"
PEOPLE_CSV = ROOT / "Bones - People Inside Businesses Data Sample.csv"


def _get_engine():
    from ltw.db import get_engine_rw
    return get_engine_rw()


# ── Firmographic → target_companies ─────────────────────────────────────────

def load_firmographic(engine) -> int:
    df = pd.read_csv(FIRMOGRAPHIC_CSV, low_memory=False, dtype=str)
    df = df.where(df.notna(), None)

    upsert_sql = text("""
        INSERT INTO target_companies (
            unique_id, company_name, trade_name, website, country, city,
            industry_code, primary_activity, employees_total, sales_volume_dollars,
            ceo_name, contact_email
        ) VALUES (
            :unique_id, :company_name, :trade_name, :website, :country, :city,
            :industry_code, :primary_activity, :employees_total, :sales_volume_dollars,
            :ceo_name, :contact_email
        )
        ON CONFLICT (unique_id) DO UPDATE SET
            company_name        = EXCLUDED.company_name,
            trade_name          = EXCLUDED.trade_name,
            website             = EXCLUDED.website,
            country             = EXCLUDED.country,
            city                = EXCLUDED.city,
            industry_code       = EXCLUDED.industry_code,
            primary_activity    = EXCLUDED.primary_activity,
            employees_total     = EXCLUDED.employees_total,
            sales_volume_dollars= EXCLUDED.sales_volume_dollars,
            ceo_name            = EXCLUDED.ceo_name,
            contact_email       = EXCLUDED.contact_email
    """)

    rows = []
    for _, row in df.iterrows():
        emp = row.get("EmployeesTotal")
        sales = row.get("SalesVolumeDollars")
        rows.append({
            "unique_id":            str(row.get("UniqueID") or "").strip() or None,
            "company_name":         str(row.get("CompanyName") or "").strip() or None,
            "trade_name":           str(row.get("TradeName") or "").strip() or None,
            "website":              str(row.get("Website") or "").strip() or None,
            "country":              str(row.get("Country") or "").strip() or None,
            "city":                 str(row.get("City") or "").strip() or None,
            "industry_code":        str(row.get("PrimaryLocalActivityCode") or "").strip() or None,
            "primary_activity":     str(row.get("InternationalLabel") or "").strip() or None,
            "employees_total":      int(float(emp)) if emp and emp != "None" else None,
            "sales_volume_dollars": float(sales) if sales and sales != "None" else None,
            "ceo_name":             str(row.get("CEOName") or "").strip() or None,
            "contact_email":        str(row.get("Email") or "").strip() or None,
        })

    # Skip rows with no unique_id
    rows = [r for r in rows if r["unique_id"]]

    with engine.begin() as conn:
        conn.execute(upsert_sql, rows)

    print(f"  ✓ target_companies: {len(rows)} rows upserted")
    return len(rows)


# ── People CSV → people ──────────────────────────────────────────────────────

def _parse_json_field(value) -> list | None:
    """Split pipe/comma separated strings into JSON arrays."""
    if value is None or str(value).strip() in ("", "nan", "None"):
        return None
    import json
    parts = [v.strip() for v in str(value).replace(";", "|").split("|") if v.strip()]
    return json.dumps(parts) if parts else None


def load_people(engine) -> int:
    df = pd.read_csv(PEOPLE_CSV, low_memory=False, dtype=str)
    df = df.where(df.notna(), None)

    # Build a lookup: company_name (lower) → unique_id from firmographic
    with engine.connect() as conn:
        result = conn.execute(text("SELECT unique_id, LOWER(company_name) AS cn FROM target_companies"))
        company_map: dict[str, str] = {row.cn: row.unique_id for row in result}

    upsert_sql = text("""
        INSERT INTO people (
            unique_id, first_name, last_name, title, email, seniority,
            department, sub_department, industry, city, state, country,
            company_name, company_city, company_country,
            employees, annual_revenue, technologies, keywords
        ) VALUES (
            :unique_id, :first_name, :last_name, :title, :email, :seniority,
            :department, :sub_department, :industry, :city, :state, :country,
            :company_name, :company_city, :company_country,
            :employees, :annual_revenue, :technologies, :keywords
        )
        ON CONFLICT DO NOTHING
    """)

    rows = []
    for _, row in df.iterrows():
        co = str(row.get("Company Name") or "").strip().lower()
        uid = company_map.get(co)
        rows.append({
            "unique_id":      uid,
            "first_name":     str(row.get("First Name") or "").strip() or None,
            "last_name":      str(row.get("Last Name") or "").strip() or None,
            "title":          str(row.get("Title") or "").strip() or None,
            "email":          str(row.get("Email") or "").strip() or None,
            "seniority":      str(row.get("Seniority") or "").strip() or None,
            "department":     str(row.get("Departments") or "").strip() or None,
            "sub_department": str(row.get("Sub Departments") or "").strip() or None,
            "industry":       str(row.get("Industry") or "").strip() or None,
            "city":           str(row.get("City") or "").strip() or None,
            "state":          str(row.get("State") or "").strip() or None,
            "country":        str(row.get("Country") or "").strip() or None,
            "company_name":   str(row.get("Company Name") or "").strip() or None,
            "company_city":   str(row.get("Company City") or "").strip() or None,
            "company_country":str(row.get("Company Country") or "").strip() or None,
            "employees":      str(row.get("# Employees") or "").strip() or None,
            "annual_revenue": str(row.get("Annual Revenue") or "").strip() or None,
            "technologies":   _parse_json_field(row.get("Technologies")),
            "keywords":       _parse_json_field(row.get("Keywords")),
        })

    with engine.begin() as conn:
        conn.execute(upsert_sql, rows)

    print(f"  ✓ people: {len(rows)} rows processed")
    return len(rows)


if __name__ == "__main__":
    print("Lead The Way — ETL")
    eng = _get_engine()
    load_firmographic(eng)
    load_people(eng)
    print("Done.")
