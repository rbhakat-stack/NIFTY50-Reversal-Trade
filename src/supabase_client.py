"""
Supabase client factory.

IMPORTANT: The service-role client must only be used in server-side /
backend code paths (data ingestion, backtest engine, alert engine). Never
import `get_service_client` from Streamlit page code that could expose
results directly to an untrusted client context.
"""
from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from src import config
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


class SupabaseConfigError(RuntimeError):
    """Raised when required Supabase environment variables are missing."""


@lru_cache(maxsize=1)
def get_service_client() -> Client:
    """Server-side client using the service role key (full read/write)."""
    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_ROLE_KEY:
        raise SupabaseConfigError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set. "
            "Supabase connection failed. Please check environment variables."
        )
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


@lru_cache(maxsize=1)
def get_anon_client() -> Client:
    """Read-only-ish client using the anon key, safe for lighter client contexts."""
    if not config.SUPABASE_URL or not config.SUPABASE_ANON_KEY:
        raise SupabaseConfigError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set. "
            "Supabase connection failed. Please check environment variables."
        )
    return create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)


def is_configured() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_SERVICE_ROLE_KEY)
