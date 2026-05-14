"""Application configuration via Pydantic Settings."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent

PRODUCT_DESCRIPTION = (
    "Lead The Way: Şirketlerin doğal dil komutlarıyla B2B iletişim "
    "veritabanlarını anlık filtreleyip, yapay zeka destekli kişiselleştirilmiş "
    "soğuk satış mesajları oluşturmasını sağlayan AI-native satış zekası platformu."
)

DEFAULT_CSV_PATH = PROJECT_ROOT / "Bones - People Inside Businesses Data Sample.csv"


class Settings(BaseSettings):
    """Runtime settings. Reads from environment / .env if present."""

    gemini_api_key: str | None = None
    supabase_url: str | None = None
    supabase_key: str | None = None  # anon/publishable key for app reads & writes
    supabase_service_key: str | None = None  # service_role key for migration script only

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


def get_settings() -> Settings:
    return Settings()
