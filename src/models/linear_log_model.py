"""
Default trend model: OLS linear regression of log(close_price) on
trading_day_index (sequential integer since the training start date).

predicted_trend_price = exp(alpha + beta * trading_day_index)

Log-price is used (rather than raw price) because index levels grow
roughly exponentially over multi-decade horizons, so a straight line in
log-space is a much better description of the long-run path than a
straight line in price-space.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from src import config
from src.models.trend_model import TrendFitResult, TrendModel
from src.utils.date_utils import add_trading_day_index


class LinearLogTrendModel(TrendModel):
    model_type = config.MODEL_TYPE_LOG_LINEAR

    def __init__(self):
        self.alpha: float | None = None
        self.beta: float | None = None
        self.r_squared: float | None = None
        self._fitted_df: pd.DataFrame | None = None

    def fit(self, df: pd.DataFrame) -> TrendFitResult:
        if len(df) < 2:
            raise ValueError("Model could not be fitted due to insufficient data.")

        indexed = add_trading_day_index(df)
        x = indexed["trading_day_index"].astype(float)
        y = np.log(indexed["close_price"].astype(float))

        x_with_const = sm.add_constant(x)
        ols_result = sm.OLS(y, x_with_const).fit()

        self.alpha = float(ols_result.params["const"])
        self.beta = float(ols_result.params["trading_day_index"])
        self.r_squared = float(ols_result.rsquared)
        self._fitted_df = indexed

        latest = indexed.iloc[-1]
        latest_predicted = self.predict(latest["trading_day_index"])
        latest_actual = float(latest["close_price"])
        latest_deviation = (latest_actual - latest_predicted) / latest_predicted

        return TrendFitResult(
            model_type=self.model_type,
            training_start_date=indexed["trade_date"].iloc[0],
            training_end_date=indexed["trade_date"].iloc[-1],
            number_of_observations=len(indexed),
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
