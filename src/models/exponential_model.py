"""
Rolling exponential trend model.

Fits a log-linear regression (same functional form as LinearLogTrendModel)
but restricted to the most recent `window_days` trading days, with
exponentially decaying weights so more recent closes influence the fitted
trend more than older ones within the window. This lets the trend line
adapt to regime changes faster than the full-history model, at the cost of
more noise sensitivity.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from src import config
from src.models.trend_model import TrendFitResult, TrendModel
from src.utils.date_utils import add_trading_day_index


class RollingExponentialTrendModel(TrendModel):
    model_type = config.MODEL_TYPE_ROLLING_EXP

    def __init__(self, window_days: int = 252, decay: float = 0.98):
        self.window_days = window_days
        self.decay = decay
        self.alpha: float | None = None
        self.beta: float | None = None
        self.r_squared: float | None = None
        self._window_start_index: int = 0

    def fit(self, df: pd.DataFrame) -> TrendFitResult:
        if len(df) < 2:
            raise ValueError("Model could not be fitted due to insufficient data.")

        indexed = add_trading_day_index(df)
        window = indexed.tail(self.window_days) if len(indexed) > self.window_days else indexed
        if len(window) < 2:
            raise ValueError("Model could not be fitted due to insufficient data.")

        self._window_start_index = int(window["trading_day_index"].iloc[0])
        x = window["trading_day_index"].astype(float)
        y = np.log(window["close_price"].astype(float))

        # Most recent observation gets weight 1.0; weights decay going backwards.
        n = len(window)
        age = np.arange(n - 1, -1, -1)
        weights = self.decay ** age

        x_with_const = sm.add_constant(x)
        wls_result = sm.WLS(y, x_with_const, weights=weights).fit()

        self.alpha = float(wls_result.params["const"])
        self.beta = float(wls_result.params["trading_day_index"])
        self.r_squared = float(wls_result.rsquared)

        latest = window.iloc[-1]
        latest_predicted = self.predict(latest["trading_day_index"])
        latest_actual = float(latest["close_price"])
        latest_deviation = (latest_actual - latest_predicted) / latest_predicted

        return TrendFitResult(
            model_type=self.model_type,
            training_start_date=window["trade_date"].iloc[0],
            training_end_date=window["trade_date"].iloc[-1],
            number_of_observations=len(window),
            intercept=self.alpha,
            coefficient=self.beta,
            r_squared=self.r_squared,
            latest_predicted_price=latest_predicted,
            latest_actual_close=latest_actual,
            latest_deviation_pct=float(latest_deviation),
        )

    def predict(self, trading_day_index):
        if self.alpha is None or self.beta is None:
            raise ValueError("Model has not been fitted yet.")
        predicted_log_price = self.alpha + self.beta * np.asarray(trading_day_index, dtype=float)
        result = np.exp(predicted_log_price)
        if np.isscalar(trading_day_index) or np.ndim(trading_day_index) == 0:
            return float(result)
        return result

    def predict_series(self, df: pd.DataFrame) -> pd.Series:
        indexed = df if "trading_day_index" in df.columns else add_trading_day_index(df)
        return pd.Series(self.predict(indexed["trading_day_index"].values), index=indexed.index)
