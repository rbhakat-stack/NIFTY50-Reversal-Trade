import numpy as np
import pytest

from src import config
from src.models.exponential_model import RollingExponentialTrendModel
from src.models.linear_log_model import LinearLogTrendModel
from src.models.polynomial_log_model import PolynomialLogTrendModel
from src.models.trend_model import get_model


def test_linear_log_model_recovers_known_trend():
    # Perfect log-linear series: close = exp(alpha + beta * index)
    import pandas as pd

    alpha, beta = np.log(100), 0.001
    n = 300
    dates = pd.bdate_range("2020-01-01", periods=n)
    close = np.exp(alpha + beta * np.arange(n))
    df = pd.DataFrame({"trade_date": [d.date() for d in dates], "close_price": close})

    model = LinearLogTrendModel()
    fit_result = model.fit(df)

    assert fit_result.r_squared > 0.999
    assert abs(fit_result.intercept - alpha) < 1e-6
    assert abs(fit_result.coefficient - beta) < 1e-8
    assert abs(fit_result.latest_deviation_pct) < 1e-6


def test_linear_log_model_insufficient_data_raises():
    import pandas as pd

    df = pd.DataFrame({"trade_date": [pd.Timestamp("2020-01-01").date()], "close_price": [100.0]})
    model = LinearLogTrendModel()
    with pytest.raises(ValueError):
        model.fit(df)


def test_deviation_calculation_matches_formula(synthetic_price_history):
    model = LinearLogTrendModel()
    fit_result = model.fit(synthetic_price_history)
    expected_deviation = (fit_result.latest_actual_close - fit_result.latest_predicted_price) / fit_result.latest_predicted_price
    assert abs(fit_result.latest_deviation_pct - expected_deviation) < 1e-9


def test_polynomial_log_model_fits(synthetic_price_history):
    model = PolynomialLogTrendModel(degree=2)
    fit_result = model.fit(synthetic_price_history)
    assert fit_result.number_of_observations == len(synthetic_price_history)
    assert 0 <= fit_result.r_squared <= 1


def test_rolling_exponential_model_uses_window_only(synthetic_price_history):
    model = RollingExponentialTrendModel(window_days=100)
    fit_result = model.fit(synthetic_price_history)
    assert fit_result.number_of_observations == 100


def test_get_model_factory_returns_correct_type():
    assert isinstance(get_model(config.MODEL_TYPE_LOG_LINEAR), LinearLogTrendModel)
    assert isinstance(get_model(config.MODEL_TYPE_POLY_LOG), PolynomialLogTrendModel)
    assert isinstance(get_model(config.MODEL_TYPE_ROLLING_EXP), RollingExponentialTrendModel)
    with pytest.raises(ValueError):
        get_model("not_a_real_model")


def test_no_look_ahead_refit_on_prefix_matches_manual_fit(synthetic_price_history):
    """Fitting on a prefix of the data must be identical to fitting on that
    prefix in isolation — i.e. the model never 'sees' rows beyond what it's given."""
    cutoff = 500
    prefix = synthetic_price_history.iloc[:cutoff].reset_index(drop=True)

    model_a = LinearLogTrendModel()
    fit_a = model_a.fit(prefix)

    model_b = LinearLogTrendModel()
    fit_b = model_b.fit(synthetic_price_history.iloc[:cutoff].reset_index(drop=True))

    assert fit_a.intercept == fit_b.intercept
    assert fit_a.coefficient == fit_b.coefficient

    # Fitting on more data (including "future" rows relative to cutoff) must change the fit.
    model_full = LinearLogTrendModel()
    fit_full = model_full.fit(synthetic_price_history)
    assert fit_full.coefficient != fit_a.coefficient
