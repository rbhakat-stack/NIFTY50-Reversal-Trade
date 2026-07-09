"""
Reusable Supabase read/write functions ("repository layer") for all six
tables. All writes use the service-role client and batch upsert/insert
where possible. Every function returns plain Python data (DataFrame or
dict/list) so callers never touch the supabase-py response objects
directly.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

from src import config
from src.supabase_client import get_service_client
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

_BATCH_SIZE = 500


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    if isinstance(value, (np.floating, np.integer)):
        value = value.item()
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return None
    return value


def _records_from_df(df: pd.DataFrame) -> list[dict]:
    records = df.replace({np.nan: None}).to_dict(orient="records")
    return [{k: _json_safe(v) for k, v in rec.items()} for rec in records]


def _batched(records: list[dict], batch_size: int = _BATCH_SIZE):
    for i in range(0, len(records), batch_size):
        yield records[i : i + batch_size]


# ---------------------------------------------------------------------------
# nifty_daily_prices
# ---------------------------------------------------------------------------
def insert_daily_prices(df: pd.DataFrame) -> int:
    """Plain insert (will error on duplicate trade_date). Prefer upsert_daily_prices."""
    client = get_service_client()
    records = _records_from_df(df)
    total = 0
    for batch in _batched(records):
        client.table(config.TABLE_PRICES).insert(batch).execute()
        total += len(batch)
    logger.info("Inserted %d price rows", total)
    return total


def upsert_daily_prices(df: pd.DataFrame) -> int:
    """Upsert by trade_date (idempotent). This is the primary write path."""
    if df.empty:
        return 0
    client = get_service_client()
    records = _records_from_df(df)
    total = 0
    for batch in _batched(records):
        client.table(config.TABLE_PRICES).upsert(batch, on_conflict="trade_date").execute()
        total += len(batch)
    logger.info("Upserted %d price rows", total)
    return total


def fetch_price_history(start_date: date | None = None, end_date: date | None = None) -> pd.DataFrame:
    client = get_service_client()
    query = client.table(config.TABLE_PRICES).select("*")
    if start_date:
        query = query.gte("trade_date", start_date.isoformat())
    if end_date:
        query = query.lte("trade_date", end_date.isoformat())
    response = query.order("trade_date", desc=False).execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return df


def fetch_latest_data_date() -> date | None:
    client = get_service_client()
    response = (
        client.table(config.TABLE_PRICES)
        .select("trade_date")
        .order("trade_date", desc=True)
        .limit(1)
        .execute()
    )
    if not response.data:
        return None
    return pd.Timestamp(response.data[0]["trade_date"]).date()


# ---------------------------------------------------------------------------
# strategy_signals
# ---------------------------------------------------------------------------
def insert_signals(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    client = get_service_client()
    records = _records_from_df(df)
    total = 0
    for batch in _batched(records):
        client.table(config.TABLE_SIGNALS).upsert(batch, on_conflict="signal_date").execute()
        total += len(batch)
    logger.info("Upserted %d signal rows", total)
    return total


def fetch_latest_signal() -> dict | None:
    client = get_service_client()
    response = (
        client.table(config.TABLE_SIGNALS)
        .select("*")
        .order("signal_date", desc=True)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def fetch_signals(start_date: date | None = None, end_date: date | None = None) -> pd.DataFrame:
    client = get_service_client()
    query = client.table(config.TABLE_SIGNALS).select("*")
    if start_date:
        query = query.gte("signal_date", start_date.isoformat())
    if end_date:
        query = query.lte("signal_date", end_date.isoformat())
    response = query.order("signal_date", desc=False).execute()
    return pd.DataFrame(response.data)


# ---------------------------------------------------------------------------
# strategy_trades
# ---------------------------------------------------------------------------
def insert_trades(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    client = get_service_client()
    schema_cols = [c for c in config.STRATEGY_TRADES_COLUMNS if c in df.columns]
    records = _records_from_df(df[schema_cols])
    total = 0
    for batch in _batched(records):
        client.table(config.TABLE_TRADES).insert(batch).execute()
        total += len(batch)
    logger.info("Inserted %d trade rows", total)
    return total


def fetch_trades(start_date: date | None = None, end_date: date | None = None) -> pd.DataFrame:
    client = get_service_client()
    query = client.table(config.TABLE_TRADES).select("*")
    if start_date:
        query = query.gte("execution_date", start_date.isoformat())
    if end_date:
        query = query.lte("execution_date", end_date.isoformat())
    response = query.order("execution_date", desc=False).execute()
    return pd.DataFrame(response.data)


# ---------------------------------------------------------------------------
# daily_strategy_state
# ---------------------------------------------------------------------------
def insert_daily_state(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    client = get_service_client()
    records = _records_from_df(df)
    total = 0
    for batch in _batched(records):
        client.table(config.TABLE_STATE).upsert(batch, on_conflict="trade_date").execute()
        total += len(batch)
    logger.info("Upserted %d daily state rows", total)
    return total


def fetch_latest_portfolio_state() -> dict | None:
    client = get_service_client()
    response = (
        client.table(config.TABLE_STATE)
        .select("*")
        .order("trade_date", desc=True)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def fetch_backtest_results(start_date: date | None = None, end_date: date | None = None) -> pd.DataFrame:
    client = get_service_client()
    query = client.table(config.TABLE_STATE).select("*")
    if start_date:
        query = query.gte("trade_date", start_date.isoformat())
    if end_date:
        query = query.lte("trade_date", end_date.isoformat())
    response = query.order("trade_date", desc=False).execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return df


# ---------------------------------------------------------------------------
# model_runs
# ---------------------------------------------------------------------------
def insert_model_run(record: dict) -> None:
    client = get_service_client()
    safe_record = {k: _json_safe(v) for k, v in record.items()}
    client.table(config.TABLE_MODEL_RUNS).insert(safe_record).execute()


def fetch_latest_model_run() -> dict | None:
    client = get_service_client()
    response = (
        client.table(config.TABLE_MODEL_RUNS)
        .select("*")
        .order("run_date", desc=True)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def fetch_model_runs(limit: int = 100) -> pd.DataFrame:
    client = get_service_client()
    response = (
        client.table(config.TABLE_MODEL_RUNS)
        .select("*")
        .order("run_date", desc=True)
        .limit(limit)
        .execute()
    )
    return pd.DataFrame(response.data)


# ---------------------------------------------------------------------------
# alert_events
# ---------------------------------------------------------------------------
def insert_alert_event(record: dict) -> None:
    client = get_service_client()
    safe_record = {k: _json_safe(v) for k, v in record.items()}
    client.table(config.TABLE_ALERTS).insert(safe_record).execute()


def alert_already_sent(alert_date: date, signal_type: str) -> bool:
    """Prevents duplicate alerts for the same signal date + signal type."""
    client = get_service_client()
    response = (
        client.table(config.TABLE_ALERTS)
        .select("id")
        .eq("alert_date", alert_date.isoformat())
        .eq("signal_type", signal_type)
        .limit(1)
        .execute()
    )
    return bool(response.data)


def fetch_alert_events(limit: int = 200) -> pd.DataFrame:
    client = get_service_client()
    response = (
        client.table(config.TABLE_ALERTS)
        .select("*")
        .order("alert_date", desc=True)
        .limit(limit)
        .execute()
    )
    return pd.DataFrame(response.data)
