import pandas as pd

from src.data.data_validator import validate_ohlc_data


def _base_df():
    return pd.DataFrame(
        {
            "trade_date": ["2020-01-01", "2020-01-02", "2020-01-03"],
            "open_price": [100.0, 101.0, 102.0],
            "high_price": [101.0, 102.0, 103.0],
            "low_price": [99.0, 100.0, 101.0],
            "close_price": [100.5, 101.5, 102.5],
            "volume": [1000, 1100, 1200],
        }
    )


def test_valid_data_passes_through_clean():
    result = validate_ohlc_data(_base_df())
    assert len(result.clean_df) == 3
    assert result.dropped_rows.empty


def test_invalid_date_is_dropped():
    df = _base_df()
    df.loc[0, "trade_date"] = "not-a-date"
    result = validate_ohlc_data(df)
    assert len(result.clean_df) == 2
    assert any("invalid" in w.lower() for w in result.warnings)


def test_non_positive_close_is_dropped():
    df = _base_df()
    df.loc[0, "close_price"] = 0
    result = validate_ohlc_data(df)
    assert len(result.clean_df) == 2


def test_non_positive_open_is_dropped():
    df = _base_df()
    df.loc[0, "open_price"] = -5
    result = validate_ohlc_data(df)
    assert len(result.clean_df) == 2


def test_high_below_low_is_dropped():
    df = _base_df()
    df.loc[0, "high_price"] = 90.0  # below low_price of 99
    result = validate_ohlc_data(df)
    assert len(result.clean_df) == 2


def test_high_below_close_is_dropped():
    df = _base_df()
    df.loc[0, "high_price"] = 100.0  # below close_price of 100.5
    result = validate_ohlc_data(df)
    assert len(result.clean_df) == 2


def test_low_above_close_is_dropped():
    df = _base_df()
    df.loc[0, "low_price"] = 101.0  # above close_price of 100.5
    result = validate_ohlc_data(df)
    assert len(result.clean_df) == 2


def test_duplicate_dates_deduplicated_keeping_last():
    df = _base_df()
    dup_row = df.iloc[[0]].copy()
    dup_row["close_price"] = 100.9
    dup_row["high_price"] = 101.5
    df = pd.concat([df, dup_row], ignore_index=True)
    result = validate_ohlc_data(df)
    assert len(result.clean_df) == 3
    kept = result.clean_df[result.clean_df["trade_date"] == pd.Timestamp("2020-01-01").date()]
    assert kept["close_price"].iloc[0] == 100.9


def test_sorted_ascending_by_date():
    df = _base_df().iloc[::-1].reset_index(drop=True)  # reverse order
    result = validate_ohlc_data(df)
    dates = result.clean_df["trade_date"].tolist()
    assert dates == sorted(dates)


def test_data_source_attached():
    result = validate_ohlc_data(_base_df(), data_source="TEST_SOURCE")
    assert (result.clean_df["data_source"] == "TEST_SOURCE").all()


def test_missing_business_days_flagged():
    df = pd.DataFrame(
        {
            "trade_date": ["2020-01-01", "2020-01-06"],  # Wed, then next Mon (skips several business days)
            "open_price": [100.0, 105.0],
            "high_price": [101.0, 106.0],
            "low_price": [99.0, 104.0],
            "close_price": [100.5, 105.5],
            "volume": [1000, 1000],
        }
    )
    result = validate_ohlc_data(df)
    assert len(result.missing_business_days) > 0
