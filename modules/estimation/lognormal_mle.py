"""
Three-parameter log-normal discharge estimator (modified MLE)
per the Polish hydrology standard, formulas 3.35–3.38.

Workflow
--------
    Q_{max,p} = ε + exp(μ + σ · u_p)                                 (3.35)

1. ε estimated from order statistics (Stedinger 1993, formula 3.36):
       ε = (Q_max(1) · Q_max(N) − median²) /
           (Q_max(1) + Q_max(N) − 2 · median)
2. μ, σ estimated by MLE on the shifted log-series ln(Q_i − ε)
   using formulas 3.37 and 3.38.

Strictly speaking this is "conditional MLE": ε is fixed via
quantile-matching, then μ, σ are the closed-form estimators on the
resulting two-parameter log-normal.  σ uses the N−1 denominator
(formula 3.38), i.e. the sample std, not the strict MLE which would
use N.  This deliberately matches the standard.
"""

from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import norm

from .base import DischargeEstimator


class LogNormal3pMLE(DischargeEstimator):
    """3-parameter log-normal, modified MLE per Polish hydrology standard."""

    distribution_id: int = 2        # Log-Normal
    estimation_method_id: int = 2   # Maximum Likelihood

    def __init__(self) -> None:
        self._epsilon: Optional[float] = None
        self._mu: Optional[float] = None
        self._sigma: Optional[float] = None
        self._n: Optional[int] = None

    # ------------------------------------------------------------------ fit
    def fit(self, timeseries: pd.Series) -> None:
        q = np.asarray(timeseries.dropna(), dtype=float)
        if q.size < 3:
            raise ValueError(f"Need at least 3 observations, got {q.size}.")
        if np.any(q <= 0):
            raise ValueError("Discharges must be strictly positive.")

        q_max = float(np.max(q))
        q_min = float(np.min(q))
        q_med = float(np.median(q))

        # ε from formula 3.36
        denom = q_max + q_min - 2.0 * q_med
        if denom == 0.0:
            raise ValueError(
                "Cannot estimate ε: max + min == 2·median "
                "(formula 3.36 is degenerate — sample is likely not log-normal)."
            )
        epsilon = (q_max * q_min - q_med ** 2) / denom

        # Physical constraint: ε must be a strict lower bound so ln(Q − ε) is defined.
        if epsilon >= q_min:
            raise ValueError(
                f"Estimated ε={epsilon:.4f} ≥ min(Q)={q_min:.4f}; "
                "3-parameter log-normal cannot be fit on this series "
                "(try the 2-parameter variant or a different distribution)."
            )

        shifted = np.log(q - epsilon)

        mu = float(np.mean(shifted))                                  # (3.37)
        sigma = float(                                                # (3.38)
            np.sqrt(np.sum((shifted - mu) ** 2) / (q.size - 1))
        )
        if sigma <= 0.0:
            raise ValueError("Computed σ is non-positive; degenerate sample.")

        self._epsilon, self._mu, self._sigma, self._n = epsilon, mu, sigma, q.size

    # -------------------------------------------------------------- estimate
    def estimate(self, return_period: int) -> float:
        self._require_fit()
        if return_period <= 1:
            raise ValueError("return_period must be > 1 year.")
        p = 1.0 / return_period                  # exceedance probability
        u_p = norm.ppf(1.0 - p)                  # u_p = Φ⁻¹(1 − p)
        return float(self._epsilon + np.exp(self._mu + self._sigma * u_p))

    # --------------------------------------------------------- fitted_params
    def fitted_params(self) -> dict[str, float]:
        self._require_fit()
        return {
            "epsilon": self._epsilon,
            "mu": self._mu,
            "sigma": self._sigma,
        }

    # -------------------------------------------------------- quantile_curve
    def quantile_curve(self, p_grid: np.ndarray) -> np.ndarray:
        self._require_fit()
        p = np.asarray(p_grid, dtype=float)
        if np.any((p <= 0.0) | (p >= 1.0)):
            raise ValueError("p_grid must contain values strictly in (0, 1).")
        u_p = norm.ppf(1.0 - p)
        return self._epsilon + np.exp(self._mu + self._sigma * u_p)

    # -------------------------------------------------------------- internal
    def _require_fit(self) -> None:
        if self._epsilon is None:
            raise RuntimeError("fit() must be called before this method.")