"""
Weibull discharge estimator (MLE) per Polish hydrology standard,
formulas 3.52–3.55.

    Q_{max,p}     = ε + (1/α_W) · (−ln p)^{1/β_W}                   (3.52)
    P(Q_max ≥ x)  = exp(−[α_W (x − ε)]^{β_W})                       (3.55)

Workflow
--------
1. ε is taken as given (constructor argument; the standard prescribes
   reading it graphically).  Pass ε = 0 for the 2-parameter Weibull.
2. β_W is the root of the MLE score equation (3.53):

        f_β(β) = 1/β + mean(ln y_i) − Σ(y_i^β · ln y_i) / Σ(y_i^β) = 0

   where y_i = Q_i − ε.  f_β is monotone decreasing → unique positive
   root; solved with Brent's method.
3. α_W follows in closed form (3.54):

        α_W = [mean(y_i^β)]^{−1/β}
"""

from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from .base import DischargeEstimator


class WeibullMLE(DischargeEstimator):
    """Weibull (2- or 3-parameter), MLE per Polish hydrology standard."""

    distribution_id: int = 6        # Weibull
    estimation_method_id: int = 2   # Maximum Likelihood

    def __init__(self, epsilon: float = 0.0) -> None:
        """
        Parameters
        ----------
        epsilon : float, default 0.0
            Lower bound of discharges, ε in formula 3.52.
            The standard expects this to be read from a probability plot.
            Use 0.0 for the 2-parameter Weibull.
        """
        if epsilon < 0:
            raise ValueError(f"epsilon must be ≥ 0 (got {epsilon}).")
        self._epsilon: float = float(epsilon)
        self._alpha: Optional[float] = None
        self._beta: Optional[float] = None
        self._n: Optional[int] = None

    # ----------------------------------------------------------------- fit
    def fit(self, timeseries: pd.Series) -> None:
        q = np.asarray(timeseries.dropna(), dtype=float)
        if q.size < 3:
            raise ValueError(f"Need at least 3 observations, got {q.size}.")
        if np.any(q <= 0):
            raise ValueError("Discharges must be strictly positive.")
        if self._epsilon >= float(np.min(q)):
            raise ValueError(
                f"epsilon={self._epsilon:.4f} ≥ min(Q)={float(np.min(q)):.4f}; "
                "shifted series y = Q − ε must be strictly positive."
            )

        y = q - self._epsilon
        log_y = np.log(y)

        if log_y.std() < 1e-12:
            raise ValueError(
                "Shifted discharges are (numerically) constant — Weibull MLE undefined."
            )

        beta = self._solve_beta(log_y)

        # α_W from (3.54), computed via log-sum-exp to avoid overflow for large β.
        log_w = beta * log_y
        L = log_w.max()
        log_mean_y_beta = L + np.log(np.mean(np.exp(log_w - L)))
        alpha = float(np.exp(-log_mean_y_beta / beta))

        self._beta = float(beta)
        self._alpha = alpha
        self._n = q.size

    # ----------------- internals: solving the MLE score equation -----------
    @staticmethod
    def _score_beta(beta: float, log_y: np.ndarray) -> float:
        """f_β(β) from formula 3.53, evaluated log-stably."""
        log_w = beta * log_y
        log_w = log_w - log_w.max()              # shift to avoid overflow
        w = np.exp(log_w)
        weighted_mean_log_y = np.sum(w * log_y) / np.sum(w)
        return 1.0 / beta + float(log_y.mean()) - weighted_mean_log_y

    def _solve_beta(self, log_y: np.ndarray) -> float:
        """Unique positive root of f_β(β); f_β is strictly decreasing."""
        lo, hi = 1e-3, 1e2
        f_lo = self._score_beta(lo, log_y)
        # f_β(0⁺) = +∞ so f_lo > 0 in practice; expand hi until sign flips.
        for _ in range(10):
            f_hi = self._score_beta(hi, log_y)
            if f_lo * f_hi < 0:
                break
            hi *= 2.0
        else:
            raise RuntimeError(
                "Could not bracket β: f_β did not change sign within (1e-3, ~1e5). "
                "Sample is likely degenerate."
            )
        return float(brentq(self._score_beta, lo, hi, args=(log_y,),
                            xtol=1e-10, rtol=1e-12))

    # -------------------------------------------------------------- estimate
    def estimate(self, return_period: int) -> float:
        self._require_fit()
        if return_period <= 1:
            raise ValueError("return_period must be > 1 year.")
        p = 1.0 / return_period
        return float(
            self._epsilon + (-np.log(p)) ** (1.0 / self._beta) / self._alpha
        )

    # --------------------------------------------------------- fitted_params
    def fitted_params(self) -> dict[str, float]:
        self._require_fit()
        return {
            "epsilon": self._epsilon,
            "alpha": self._alpha,
            "beta": self._beta,
        }

    # -------------------------------------------------------- quantile_curve
    def quantile_curve(self, p_grid: np.ndarray) -> np.ndarray:
        self._require_fit()
        p = np.asarray(p_grid, dtype=float)
        if np.any((p <= 0.0) | (p >= 1.0)):
            raise ValueError("p_grid must contain values strictly in (0, 1).")
        return self._epsilon + (-np.log(p)) ** (1.0 / self._beta) / self._alpha

    # -------------------------------------------------------------- internal
    def _require_fit(self) -> None:
        if self._beta is None:
            raise RuntimeError("fit() must be called before this method.")