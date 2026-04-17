"""
Log-Normal distribution fitted by the Method of Moments.

The two-parameter Log-Normal model assumes that ln(Q) ~ N(μ, σ²).
Method of Moments equates the sample mean and variance of ln(Q) to the
theoretical moments, giving direct closed-form parameter estimates:

    μ  = mean(ln Q_i)
    σ  = std(ln Q_i, ddof=1)

The T-year quantile is then:

    Q_T = exp(μ + z_{1-1/T} · σ)

where z_p is the standard normal quantile at exceedance probability p.

distribution_id    : 2  (Log-Normal in the distributions catalogue)
estimation_method_id: 1  (Method of Moments in the estimation_methods catalogue)
"""

import math

import numpy as np
import pandas as pd
from scipy import stats

from .base import DischargeEstimator


class LogNormalMoM(DischargeEstimator):
    """Log-Normal distribution, parameters estimated by Method of Moments."""

    distribution_id = 2
    estimation_method_id = 1

    def __init__(self) -> None:
        self._mu: float = float("nan")
        self._sigma: float = float("nan")
        self._n: int = 0

    def fit(self, timeseries: pd.Series) -> None:
        positive = timeseries[timeseries > 0]
        if len(positive) < 3:
            raise ValueError(f"Need at least 3 positive values, got {len(positive)}")
        log_values = np.log(positive.to_numpy(dtype=float))
        self._mu = float(log_values.mean())
        self._sigma = float(log_values.std(ddof=1))
        self._n = len(positive)

    def estimate(self, return_period: int) -> float:
        if math.isnan(self._mu):
            raise RuntimeError("fit() must be called before estimate()")
        if return_period < 2:
            raise ValueError(f"return_period must be >= 2, got {return_period}")
        exceedance_prob = 1.0 - 1.0 / return_period
        z = float(stats.norm.ppf(exceedance_prob))
        return math.exp(self._mu + z * self._sigma)

    def fitted_params(self) -> dict[str, float]:
        if math.isnan(self._mu):
            raise RuntimeError("fit() must be called before fitted_params()")
        return {"mu_log": self._mu, "sigma_log": self._sigma, "n": float(self._n)}

    def quantile_curve(self, p_grid: np.ndarray) -> np.ndarray:
        if math.isnan(self._mu):
            raise RuntimeError("fit() must be called before quantile_curve()")
        z = stats.norm.ppf(1.0 - p_grid)
        return np.exp(self._mu + self._sigma * z)
