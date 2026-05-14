"""Migrate Cogaltilmis_People_Inside_Businesses.csv → Supabase.

BEFORE RUNNING:
1. Run scripts/schema.sql in Supabase Dashboard → SQL Editor
2. In Supabase Dashboard → Table Editor, disable RLS for:
   - target_companies
   - people
   - audit_log
3. Run:  cd "Lead The Way" && .venv\\Scripts\\python.exe scripts/migrate_to_supabase.py

The script is idempotent: companies are upserted (on conflict update);
people rows are inserted fresh (duplicate runs will create duplicate people rows —
truncate the people table first if re-running).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from ltw.db import get_supabase_client  # noqa: E402 — needs dotenv first


# ── Config ──────────────────────────────────────────────────────────────────
CSV_PATH = ROOT / "Cogaltilmis_People_Inside_Businesses.csv"
BATCH_SIZE = 50          # Supabase REST batch insert limit (safe default)


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_unique_id(company_name: str, website: str) -> str:
    """Deterministic 12-char ID from company name + website."""
    raw = f"{company_name.strip().lower()}|{website.strip().lower()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def split_csv_list(value) -> list[str]:
    """Turn a comma-separated string (or NaN) into a clean list."""
    if pd.isna(value) or str(value).strip() == "":
        return []
    return [v.strip() for v in str(value).split(",") if v.strip()]


def safe_str(value, maxlen: int = 255) -> str | None:
    if pd.isna(value) or str(value).strip() in ("", "nan"):
        return None
    return str(value).strip()[:maxlen]


def safe_int(value) -> int | None:
    try:
        v = int(float(str(value)))
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def safe_float(value) -> float | None:
    try:
        v = float(str(value))
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


# ── Load CSV ─────────────────────────────────────────────────────────────────

print(f"Reading {CSV_PATH.name} …")
df = pd.read_csv(CSV_PATH, low_memory=False, encoding="utf-8-sig")
# Strip BOM / leading spaces from column names
df.columns = [c.strip() for c in df.columns]
print(f"  {len(df):,} rows, {len(df.columns)} columns")


# ── Build target_companies (one row per unique company) ───────────────────────

print("\nBuilding company records …")
company_rows: dict[str, dict] = {}

for _, row in df.iterrows():
    name = str(row.get("Company Name", "") or "").strip()
    website = str(row.get("Website", "") or "").strip()
    if not name:
        continue
    uid = make_unique_id(name, website)
    if uid in company_rows:
        continue  # already seen this company

    company_rows[uid] = {
        "unique_id":            uid,
        "company_name":         safe_str(name, 255),
        "trade_name":           safe_str(row.get("Company Name for Emails"), 255),
        "website":              safe_str(website, 255),
        "country":              safe_str(row.get("Company Country"), 50),
        "city":                 safe_str(row.get("Company City"), 100),
        "industry_code":        safe_str(row.get("Industry"), 50),
        "primary_activity":     safe_str(row.get("Industry"), 500),
        "employees_total":      safe_int(row.get("# Employees")),
        "sales_volume_dollars": safe_float(row.get("Annual Revenue")),
        "company_phone":        safe_str(row.get("Company Phone"), 50),
        "company_address":      safe_str(row.get("Company Address"), 500),
        "company_linkedin_url": safe_str(row.get("Company Linkedin Url"), 255),
        "facebook_url":         safe_str(row.get("Facebook Url"), 255),
        "twitter_url":          safe_str(row.get("Twitter Url"), 255),
    }

companies = list(company_rows.values())
print(f"  {len(companies):,} unique companies")


# ── Build people rows ─────────────────────────────────────────────────────────

print("\nBuilding people records …")
people_rows: list[dict] = []

for _, row in df.iterrows():
    name = str(row.get("Company Name", "") or "").strip()
    website = str(row.get("Website", "") or "").strip()
    uid = make_unique_id(name, website) if name else None

    people_rows.append({
        "unique_id":            uid,
        "first_name":           safe_str(row.get("First Name"), 100),
        "last_name":            safe_str(row.get("Last Name"), 100),
        "title":                safe_str(row.get("Title"), 255),
        "email":                safe_str(row.get("Email"), 255),
        "phone":                safe_str(row.get("Corporate Phone"), 50),
        "seniority":            safe_str(row.get("Seniority"), 100),
        "department":           safe_str(row.get("Departments"), 255),
        "sub_department":       safe_str(row.get("Sub Departments"), 255),
        "industry":             safe_str(row.get("Industry"), 255),
        "city":                 safe_str(row.get("City"), 100),
        "state":                safe_str(row.get("State"), 100),
        "country":              safe_str(row.get("Country"), 100),
        "linkedin_url":         safe_str(row.get("Person Linkedin Url"), 255),
        "company_name":         safe_str(name, 255),
        "company_city":         safe_str(row.get("Company City"), 100),
        "company_state":        safe_str(row.get("Company State"), 100),
        "company_country":      safe_str(row.get("Company Country"), 100),
        "company_phone":        safe_str(row.get("Company Phone"), 50),
        "company_address":      safe_str(row.get("Company Address"), 500),
        "company_linkedin_url": safe_str(row.get("Company Linkedin Url"), 255),
        "facebook_url":         safe_str(row.get("Facebook Url"), 255),
        "twitter_url":          safe_str(row.get("Twitter Url"), 255),
        "employees":            safe_str(row.get("# Employees"), 50),
        "annual_revenue":       safe_str(row.get("Annual Revenue"), 50),
        "technologies":         json.dumps(split_csv_list(row.get("Technologies")), ensure_ascii=False),
        "keywords":             json.dumps(split_csv_list(row.get("Keywords")), ensure_ascii=False),
        "opt_out":              False,
    })

print(f"  {len(people_rows):,} people records")


# ── Upload to Supabase ────────────────────────────────────────────────────────

print("\nConnecting to Supabase …")
# Use service_role key if available; otherwise fall back to anon key (needs RLS OFF)
client = get_supabase_client(svc=True)

# 1. Upsert companies
print(f"Upserting {len(companies):,} companies in batches of {BATCH_SIZE} …")
for i in range(0, len(companies), BATCH_SIZE):
    batch = companies[i: i + BATCH_SIZE]
    client.table("target_companies").upsert(
        batch, on_conflict="unique_id"
    ).execute()
    print(f"  companies {i + 1}–{min(i + BATCH_SIZE, len(companies))} ✓")

# 2. Insert people
print(f"\nInserting {len(people_rows):,} people in batches of {BATCH_SIZE} …")
for i in range(0, len(people_rows), BATCH_SIZE):
    batch = people_rows[i: i + BATCH_SIZE]
    client.table("people").insert(batch).execute()
    print(f"  people {i + 1}–{min(i + BATCH_SIZE, len(people_rows))} ✓")

print("\n✅ Migration complete.")
print(f"   Companies : {len(companies):,}")
print(f"   People    : {len(people_rows):,}")
print("\nNext steps:")
print("  1. Verify row counts in Supabase Dashboard → Table Editor")
print("  2. Start the app:  .venv\\Scripts\\python.exe -m streamlit run app.py")
