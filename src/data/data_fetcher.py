"""
Data ingestion: primary source is NSE/Nifty Indices historical data, with a
Yahoo Finance (`^NSEI`) fallback, and manual CSV as the last resort. All
functions return a raw DataFrame with columns
[trade_date, open_price, high_price, low_price, close_price, volume];
validation happens separately in `data_validator.validate_ohlc_data`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, TypeVar

import pandas as pd

from src import config
from src.data.data_repository import fetch_latest_data_date, upsert_daily_prices
from src.data.data_validator import validate_ohlc_data
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

_T = TypeVar("_T")
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 2.0


class DataSourceError(RuntimeError):
    """Raised when a data source cannot be reached or returns no usable data."""


def _with_retries(fn: Callable[[], _T], source_name: str, max_attempts: int = _MAX_ATTEMPTS) -> _T:
    """
    Both NSE (niftyindices.com scraping) and Yahoo Finance's unofficial API are
    known to intermittently return empty/malformed responses under rate
    limiting rather than a clean HTTP error, especially for large historical
    pulls. Retry a few times with a short backoff before giving up so a single
    transient hiccup doesn't surface as "data source failed" to the user.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except DataSourceError as exc:
            last_exc = exc
            if attempt < max_attempts:
                logger.warning(
                    "%s attempt %d/%d failed (%s); retrying in %.1fs...",
                    source_name,
                    attempt,
                    max_attempts,
                    exc,
                    _RETRY_BACKOFF_SECONDS,
                )
                time.sleep(_RETRY_BACKOFF_SECONDS)
    raise last_exc  # noqa: RSE102 - re-raise the last observed failure after retries are exhausted


_MIN_YFINANCE_VERSION = (1, 5, 1)


def _parse_version(version_str: str) -> tuple[int, ...]:
    parts = []
    for part in version_str.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def diagnose_data_source_environment() -> dict:
    """
    Surfaces the exact Python interpreter and package versions this process is
    running with. Both external data sources (NSE via nsepython, Yahoo
    Finance) fail in ways that look identical from the UI whether the cause is
    a real outage or simply the app running under the wrong Python
    environment (e.g. a global interpreter instead of the project's `.venv`,
    which is missing `nsepython` and/or has an outdated `yfinance` that Yahoo
    silently rejects). This makes that distinction visible instead of forcing
    a guess from a generic error message.
    """
    import sys

    info: dict = {
        "python_executable": sys.executable,
        "likely_wrong_interpreter": ".venv" not in sys.executable.replace("\\", "/"),
    }

    try:
        import yfinance as yf

        info["yfinance_version"] = getattr(yf, "__version__", "unknown")
        info["yfinance_version_ok"] = _parse_version(info["yfinance_version"]) >= _MIN_YFINANCE_VERSION
    except ImportError:
        info["yfinance_version"] = None
        info["yfinance_version_ok"] = False

    try:
        import nsepython  # noqa: F401

        info["nsepython_installed"] = True
    except ImportError:
        info["nsepython_installed"] = False

    return info


def fetch_nifty_from_yfinance(start_date: date, end_date: date) -> pd.DataFrame:
    import yfinance as yf

    def _attempt() -> pd.DataFrame:
        ticker = yf.Ticker(config.YFINANCE_SYMBOL)
        result = ticker.history(start=start_date.isoformat(), end=(end_date + timedelta(days=1)).isoformat())
        if result.empty:
            raise DataSourceError(f"Yahoo Finance returned no data for {config.YFINANCE_SYMBOL}.")
        return result

    raw = _with_retries(_attempt, config.DATA_SOURCE_YFINANCE)
    raw = raw.reset_index()
    raw = raw.rename(
        columns={
            "Date": "trade_date",
            "Open": "open_price",
            "High": "high_price",
            "Low": "low_price",
            "Close": "close_price",
            "Volume": "volume",
        }
    )
    raw["trade_date"] = pd.to_datetime(raw["trade_date"]).dt.date
    raw["data_source"] = config.DATA_SOURCE_YFINANCE
    return raw[["trade_date", "open_price", "high_price", "low_price", "close_price", "volume", "data_source"]]


def fetch_nifty_from_nse(start_date: date, end_date: date) -> pd.DataFrame:
    """
    Primary source: NSE / Nifty Indices historical data via `nsepython`.
    Raises DataSourceError on any failure so the caller can fall back to
    Yahoo Finance.
    """
    try:
        from nsepython import index_history
    except ImportError as exc:
        raise DataSourceError("nsepython is not installed; cannot query NSE directly.") from exc

    def _attempt() -> pd.DataFrame:
        try:
            result = index_history("NIFTY 50", start_date.strftime("%d-%b-%Y"), end_date.strftime("%d-%b-%Y"))
        except Exception as exc:  # network / API errors from nsepython
            raise DataSourceError(f"NSE data fetch failed: {exc}") from exc
        if result is None or result.empty:
            raise DataSourceError("NSE returned no data for the requested range.")
        return result

    raw = _with_retries(_attempt, config.DATA_SOURCE_NSE)

    raw = raw.rename(
        columns={
            "HistoricalDate": "trade_date",
            "OPEN": "open_price",
            "HIGH": "high_price",
            "LOW": "low_price",
            "CLOSE": "close_price",
            "TRADED_QUANTITY": "volume",
        }
    )
    raw["trade_date"] = pd.to_datetime(raw["trade_date"]).dt.date
    raw["data_source"] = config.DATA_SOURCE_NSE
    keep_cols = [c for c in ["trade_date", "open_price", "high_price", "low_price", "close_price", "volume", "data_source"] if c in raw.columns]
    return raw[keep_cols]


@dataclass
class RefreshResult:
    success: bool
    source_used: str | None
    rows_upserted: int
    warnings: list[str]
    error: str | None = None


def upsert_prices_to_supabase(df: pd.DataFrame, data_source: str) -> int:
    validation = validate_ohlc_data(df, data_source=data_source)
    if not validation.is_valid:
        raise DataSourceError("No valid rows remained after validation; nothing was written to Supabase.")
    return upsert_daily_prices(validation.clean_df)


def refresh_latest_nifty_data(lookback_buffer_days: int = 10) -> RefreshResult:
    """
    Daily incremental update. Fetches from the last known trade_date - buffer
    (to catch any late corrections) through today, trying NSE first and
    Yahoo Finance as fallback. Never uses future data: end_date is always
    today's date at the latest.
    """
    warnings: list[str] = []
    latest_date = fetch_latest_data_date()
    start_date = (latest_date - timedelta(days=lookback_buffer_days)) if latest_date else config.HISTORICAL_START_DATE
    end_date = date.today()

    if start_date > end_date:
        return RefreshResult(success=True, source_used=None, rows_upserted=0, warnings=["Data is already up to date."])

    for source_name, fetch_fn in (
        (config.DATA_SOURCE_NSE, fetch_nifty_from_nse),
        (config.DATA_SOURCE_YFINANCE, fetch_nifty_from_yfinance),
    ):
        try:
            raw_df = fetch_fn(start_date, end_date)
            validation = validate_ohlc_data(raw_df, data_source=source_name)
            warnings.extend(validation.warnings)
            if not validation.is_valid:
                warnings.append(f"{source_name} returned data but none passed validation.")
                continue
            rows = upsert_daily_prices(validation.clean_df)
            logger.info("Refreshed %d rows from %s", rows, source_name)
            return RefreshResult(success=True, source_used=source_name, rows_upserted=rows, warnings=warnings)
        except DataSourceError as exc:
            warnings.append(f"Data refresh failed from {source_name}: {exc}")
            logger.warning("Source %s failed: %s", source_name, exc)
            continue

    return RefreshResult(
        success=False,
        source_used=None,
        rows_upserted=0,
        warnings=warnings,
        error="All data sources failed. Latest NIFTY data is not available yet.",
    )
