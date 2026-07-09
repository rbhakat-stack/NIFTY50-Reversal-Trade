"""
Base interface for all trend models plus a factory function.

CRITICAL no-look-ahead rule: `fit(df)` must only ever be called with rows
whose trade_date <= the date being scored. Callers (signal_engine /
backtest_engine) are responsible for slicing the DataFrame before calling
fit; the models themselves do not know "today" and will happily fit on
whatever they are given.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

from src import config


@dataclass
class TrendFitResult:
    model_type: str
    training_start_date: object
    training_end_date: object
    number_of_observations: int
    intercept: float
    coefficient: float
    r_squared: float
    latest_predicted_price: float
    latest_actual_close: float
    latest_deviation_pct: float


class TrendModel(ABC):
    """Common interface implemented by every trend model variant."""

    model_type: str

    @abstractmethod
    def fit(self, df: pd.DataFrame) -> TrendFitResult:
        """
        df must contain columns [trade_date, close_price], sorted ascending,
        already truncated to only include data available as of the fit date.
        """

    @abstractmethod
    def predict(self, trading_day_index) -> float | pd.Series:
        """Predicted trend price for the given trading_day_index (or array of them)."""

    @abstractmethod
    def predict_series(self, df: pd.DataFrame) -> pd.Series:
        """Predicted trend price for every row in df (must contain trading_day_index)."""


def get_model(model_type: str, **kwargs) -> TrendModel:
    from src.models.exponential_model import RollingExponentialTrendModel
    from src.models.linear_log_model import LinearLogTrendModel
    from src.models.polynomial_log_model import PolynomialLogTrendModel

    if model_type == config.MODEL_TYPE_LOG_LINEAR:
        return LinearLogTrendModel()
    if model_type == config.MODEL_TYPE_POLY_LOG:
        return PolynomialLogTrendModel(degree=kwargs.get("degree", 2))
    if model_type == config.MODEL_TYPE_ROLLING_EXP:
        return RollingExponentialTrendModel(window_days=kwargs.get("window_days", 252))
    raise ValueError(f"Unknown model_type: {model_type}")
