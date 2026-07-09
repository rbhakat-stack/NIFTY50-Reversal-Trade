"""Manual CSV upload fallback. Expected schema: date, open, high, low, close, volume."""
from __future__ import annotations

import io

import pandas as pd

from src import config
from src.data.data_validator import ValidationResult, validate_ohlc_data

EXPECTED_COLUMNS = {"date", "open", "high", "low", "close"}


def load_nifty_from_csv(file) -> ValidationResult:
    """
    file: a file-like object (e.g. Streamlit's UploadedFile) or a path string.
    Returns a ValidationResult so the caller can decide whether to merge into
    Supabase, and can show warnings/dropped rows to the user before doing so.
    """
    if hasattr(file, "read"):
        raw = file.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        df = pd.read_csv(io.StringIO(raw))
    else:
        df = pd.read_csv(file)

    df.columns = [c.strip().lower() for c in df.columns]
    missing_cols = EXPECTED_COLUMNS - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"CSV upload validation failed: missing required columns {sorted(missing_cols)}. "
            "Expected schema: date, open, high, low, close, volume"
        )

    return validate_ohlc_data(df, data_source=config.DATA_SOURCE_CSV)
