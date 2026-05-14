"""Supabase client factory and audit-log helper.

All database I/O goes through the supabase-py client.
Two access levels:
  get_supabase_client()         → anon/publishable key  (reads + audit_log inserts)
  get_supabase_client(svc=True) → service_role key      (migration script only)
"""
from __future__ import annotations

import hashlib
from functools import lru_cache

from supabase import Client, create_client

from .config import get_settings


@lru_cache(maxsize=2)
def get_supabase_client(svc: bool = False) -> Client:
    """Return a cached Supabase client.

    Args:
        svc: If True, use the service_role key for full write access.
             Only used in the migration script — never in app runtime.
    """
    s = get_settings()
    url = (s.supabase_url or "").strip()
    if not url:
        raise RuntimeError("SUPABASE_URL is not set. Add it to your .env file.")

    if svc:
        key = (s.supabase_service_key or "").strip()
        if not key:
            # Fall back to anon key when service key is absent (RLS must be OFF)
            key = (s.supabase_key or "").strip()
    else:
        key = (s.supabase_key or "").strip()

    if not key:
        raise RuntimeError("SUPABASE_KEY is not set. Add it to your .env file.")

    return create_client(url, key)


def db_available() -> bool:
    """Return True when SUPABASE_URL is configured (Supabase mode active)."""
    return bool((get_settings().supabase_url or "").strip())


def _hash_email(email: str | None) -> str | None:
    """One-way SHA-256 hash of an email for KVKK-compliant audit logging."""
    if not email:
        return None
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]


def write_audit_log(
    event_type: str,
    company_name: str | None = None,
    person_email: str | None = None,
    query_summary: str | None = None,
    model_used: str | None = None,
    injection_flagged: bool = False,
) -> None:
    """Insert one row into audit_log (fire-and-forget; silently skips if DB unavailable)."""
    if not db_available():
        return
    try:
        client = get_supabase_client()
        client.table("audit_log").insert({
            "event_type":       event_type,
            "company_name":     (company_name or "")[:255] or None,
            "person_email":     _hash_email(person_email),
            "query_summary":    (query_summary or "")[:200] or None,
            "model_used":       (model_used or "")[:100] or None,
            "injection_flagged": injection_flagged,
        }).execute()
    except Exception:
        pass  # Audit log is non-blocking; never crash the main flow

