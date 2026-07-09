"""
OHLC data validation.

Validation never silently drops data without a record of what happened —
every dropped row and every warning is returned to the caller so the UI can
surface it (per the "surface missing data warnings" requirement).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from src.utils.date_utils import find_missing_business_days

REQUIRED_COLUMNS = ["trade_date", "open_price", "high_price", "low_price", "close_price"]


@dataclass
class ValidationResult:
    clean_df: pd.DataFrame
    dropped_rows: pd.DataFrame
    warnings: list[str] = field(default_factory=list)
    missing_business_days: list[date] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.clean_df.empty


def _coerce_schema(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    rename_map = {
        "date": "trade_date",
        "open": "open_price",
        "high": "high_price",
        "low": "low_price",
        "close": "close_price",
        "volume": "volume",
    }
    out = out.rename(columns={k: v for k, v in rename_map.items() if k in out.columns})
    missing = [c for c in REQUIRED_COLUMNS if c not in out.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    if "volume" not in out.columns:
        out["volume"] = np.nan
    return out


def validate_ohlc_data(df: pd.DataFrame, data_source: str | None = None) -> ValidationResult:
    """
    Apply all data quality rules and return a ValidationResult containing a
    clean, sorted, de-duplicated DataFrame plus a full audit trail of
    dropped rows and warnings.
    """
    warnings: list[str] = []
    df = _coerce_schema(df)

    # Date must be valid.
    parsed_dates = pd.to_datetime(df["trade_date"], errors="coerce")
    invalid_date_mask = parsed_dates.isna()
    if invalid_date_mask.any():
        warnings.append(f"Dropped {int(invalid_date_mask.sum())} rows with invalid/unparseable dates.")
    df = df.loc[~invalid_date_mask].copy()
    df["trade_date"] = parsed_dates.loc[~invalid_date_mask].dt.date

    numeric_cols = ["open_price", "high_price", "low_price", "close_price", "volume"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    dropped_frames = []

    # Close and open must be > 0.
    invalid_price_mask = (df["close_price"] <= 0) | df["close_price"].isna() | (df["open_price"] <= 0) | df["open_price"].isna()
    if invalid_price_mask.any():
        dropped_frames.append(df.loc[invalid_price_mask])
        warnings.append(f"Dropped {int(invalid_price_mask.sum())} rows with non-positive or missing open/close price.")
    df = df.loc[~invalid_price_mask].copy()

    # High >= Low, High >= Close, Low <= Close (only checked where high/low present).
    has_hl = df["high_price"].notna() & df["low_price"].notna()
    hl_violation = has_hl & (df["high_price"] < df["low_price"])
    high_close_violation = df["high_price"].notna() & (df["high_price"] < df["close_price"])
    low_close_violation = df["low_price"].notna() & (df["low_price"] > df["close_price"])
    anomaly_mask = hl_violation | high_close_violation | low_close_violation
    if anomaly_mask.any():
        dropped_frames.append(df.loc[anomaly_mask])
        warnings.append(
            f"Dropped {int(anomaly_mask.sum())} rows failing OHLC consistency checks "
            "(high>=low, high>=close, low<=close)."
        )
    df = df.loc[~anomaly_mask].copy()

    # Duplicate dates: keep the last occurrence (assumed most recently ingested/corrected).
    dup_mask = df.duplicated(subset="trade_date", keep="last")
    if dup_mask.any():
        dropped_frames.append(df.loc[dup_mask])
        warnings.append(f"Dropped {int(dup_mask.sum())} duplicate-date rows (kept latest).")
    df = df.loc[~dup_mask].copy()

    # Sort ascending.
    df = df.sort_values("trade_date").reset_index(drop=True)

    if data_source:
        df["data_source"] = data_source

    dropped_df = pd.concat(dropped_frames, ignore_index=True) if dropped_frames else pd.DataFrame()

    missing_days: list[date] = []
    if not df.empty:
        missing_days = find_missing_business_days(df["trade_date"], df["trade_date"].min(), df["trade_date"].max())
        if missing_days:
            warnings.append(
                f"{len(missing_days)} business day(s) between "
                f"{df['trade_date'].min()} and {df['trade_date'].max()} have no data "
                "(may be exchange holidays or a genuine data gap — please review)."
            )

    return ValidationResult(
        clean_df=df,
        dropped_rows=dropped_df,
        warnings=warnings,
        missing_business_days=missing_days,
    )
