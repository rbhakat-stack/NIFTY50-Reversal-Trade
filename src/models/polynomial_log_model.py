"""
Polynomial regression on log closing price:
y = log(close_price), x = trading_day_index
y = a0 + a1*x + a2*x^2 + ... + an*x^n

Allows the long-run trend to curve (e.g. capture a slowing/accelerating
growth regime) rather than assuming a single constant compounding rate for
the entire multi-decade history.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
from sklearn.preprocessing import PolynomialFeatures

from src import config
from src.models.trend_model import TrendFitResult, TrendModel
from src.utils.date_utils import add_trading_day_index


class PolynomialLogTrendModel(TrendModel):
    model_type = config.MODEL_TYPE_POLY_LOG

    def __init__(self, degree: int = 2):
        self.degree = degree
        self._poly = PolynomialFeatures(degree=degree, include_bias=False)
        self._reg = LinearRegression()
        self.r_squared: float | None = None
        self._fitted = False

    def fit(self, df: pd.DataFrame) -> TrendFitResult:
        if len(df) < self.degree + 2:
            raise ValueError("Model could not be fitted due to insufficient data.")

        indexed = add_trading_day_index(df)
        x = indexed["trading_day_index"].astype(float).values.reshape(-1, 1)
        y = np.log(indexed["close_price"].astype(float).values)

        x_poly = self._poly.fit_transform(x)
        self._reg.fit(x_poly, y)
        self._fitted = True

        y_pred = self._reg.predict(x_poly)
        self.r_squared = float(r2_score(y, y_pred))

        latest = indexed.iloc[-1]
        latest_predicted = self.predict(latest["trading_day_index"])
        latest_actual = float(latest["close_price"])
        latest_deviation = (latest_actual - latest_predicted) / latest_predicted

        return TrendFitResult(
            model_type=self.model_type,
            training_start_date=indexed["trade_date"].iloc[0],
            training_end_date=indexed["trade_date"].iloc[-1],
            number_of_observations=len(indexed),
            intercept=float(self._reg.intercept_),
            coefficient=float(self._reg.coef_[0]),
            r_squared=self.r_squared,
            latest_predicted_price=latest_predicted,
            latest_actual_close=latest_actual,
            latest_deviation_pct=float(latest_deviation),
        )

    def predict(self, trading_day_index):
        if not self._fitted:
            raise ValueError("Model has not been fitted yet.")
        x = np.atleast_1d(np.asarray(trading_day_index, dtype=float)).reshape(-1, 1)
        x_poly = self._poly.transform(x)
        predicted_log_price = self._reg.predict(x_poly)
        result = np.exp(predicted_log_price)
        if np.isscalar(trading_day_index) or np.ndim(trading_day_index) == 0:
            return float(result[0])
        return result

    def predict_series(self, df: pd.DataFrame) -> pd.Series:
        indexed = df if "trading_day_index" in df.columns else add_trading_day_index(df)
        return pd.Series(self.predict(indexed["trading_day_index"].values), index=indexed.index)
