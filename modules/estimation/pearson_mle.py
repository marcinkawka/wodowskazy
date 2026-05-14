"""
Pearson Type III with Maximum Likelihood Estimation (profile likelihood over ε).

Implements the three-parameter Pearson III distribution following the SHP
("Stowarzyszenie Hydrologów Polskich") textbook (Banasik et al.), with one
deviation: the lower-bound parameter ε is estimated by profile likelihood on
a grid rather than by the graphical eyeball method recommended in §3.16.

For each candidate ε on a grid in (0, Q_min):
    1. Compute conditional MLE of (lam, alpha) using textbook formulas (3.17-3.19):
         A_lam = ln(mean(Q-eps)) - mean(ln(Q-eps))
         lam   = (1 + sqrt(1 + 4 A_lam / 3)) / (4 A_lam)      [Thom 1958]
         alpha = lam / mean(Q-eps)
    2. Compute the joint log-likelihood at (eps, lam, alpha).

eps* is the grid point that maximises the log-likelihood; (lam*, alpha*) come from
the conditional MLE at ε*. The grid itself is exposed via profile_likelihood()
for diagnostics — a flat or monotonic L(ε) is a sign that the data do not
identify the lower bound well and a 2-parameter distribution may be a better fit.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import gammaln

from .base import DischargeEstimator


class PearsonIIIMLE(DischargeEstimator):
    """Pearson III, three-parameter MLE via profile likelihood over ε."""

    distribution_id: int = 3  # Pearson III
    estimation_method_id: int = 2  # MLE

    # Default grid resolution; override via constructor for finer/coarser search
    DEFAULT_GRID_SIZE = 200

    # Upper bound of ε grid as fraction of Q_min (must be < 1 to keep log finite)
    EPSILON_UPPER_FRACTION = 0.999

    # Lower bound of ε grid as fraction of Q_min (avoid degenerate 2-param case)
    EPSILON_LOWER_FRACTION = 1e-4

    def __init__(self, grid_size: int = DEFAULT_GRID_SIZE):
        self._grid_size = grid_size
        self._epsilon: float | None = None
        self._lambda: float | None = None
        self._alpha: float | None = None
        self._loglik: float | None = None
        self._profile_eps: np.ndarray | None = None
        self._profile_ll: np.ndarray | None = None

    # ------------------------------------------------------------------ fit

    def fit(self, timeseries: pd.Series) -> None:
        q = timeseries.to_numpy(dtype=float)
        q = q[np.isfinite(q) & (q > 0)]
        if len(q) < 3:
            raise ValueError(f"Need at least 3 positive values, got {len(q)}")

        q_min = q.min()
        eps_grid = np.linspace(
            q_min * self.EPSILON_LOWER_FRACTION,
            q_min * self.EPSILON_UPPER_FRACTION,
            self._grid_size,
        )

        ll = np.full(self._grid_size, -np.inf)
        lam_grid = np.full(self._grid_size, np.nan)
        alpha_grid = np.full(self._grid_size, np.nan)

        for i, eps in enumerate(eps_grid):
            try:
                lam, alpha = self._conditional_mle(q, eps)
            except (ValueError, FloatingPointError):
                continue
            if not (np.isfinite(lam) and np.isfinite(alpha) and lam > 0 and alpha > 0):
                continue
            lam_grid[i] = lam
            alpha_grid[i] = alpha
            ll[i] = self._loglik_pearson3(q, eps, lam, alpha)

        if not np.any(np.isfinite(ll)):
            raise RuntimeError(
                "Profile likelihood is undefined everywhere on the grid; "
                "Pearson III may be inappropriate for this series."
            )

        i_best = int(np.argmax(ll))
        self._epsilon = float(eps_grid[i_best])
        self._lambda = float(lam_grid[i_best])
        self._alpha = float(alpha_grid[i_best])
        self._loglik = float(ll[i_best])
        self._profile_eps = eps_grid
        self._profile_ll = ll

    # ------------------------------------------------------------ internals

    @staticmethod
    def _conditional_mle(q: np.ndarray, eps: float) -> tuple[float, float]:
        """MLE of (lam, alpha) given fixed eps — textbook formulas (3.17-3.19)."""
        d = q - eps  # all > 0 because eps < q_min
        mean_d = d.mean()
        mean_log_d = np.log(d).mean()
        a_lam = np.log(mean_d) - mean_log_d
        if a_lam <= 0:
            # Jensen guarantees a_lam ≥ 0; non-positive means numerical noise
            # in a near-degenerate sample.
            raise ValueError("A_λ non-positive; cannot estimate shape")
        lam = (1.0 + np.sqrt(1.0 + 4.0 * a_lam / 3.0)) / (4.0 * a_lam)
        alpha = lam / mean_d
        return lam, alpha

    @staticmethod
    def _loglik_pearson3(q: np.ndarray, eps: float, lam: float, alpha: float) -> float:
        """Joint log-likelihood for Pearson III at (eps, lam, alpha)."""
        d = q - eps
        n = len(q)
        return (
            n * lam * np.log(alpha)
            - n * gammaln(lam)
            + (lam - 1.0) * np.log(d).sum()
            - alpha * d.sum()
        )

    def _ensure_fitted(self) -> None:
        if self._epsilon is None:
            raise RuntimeError("fit() must be called before this method")

    # --------------------------------------------------------- public API

    def estimate(self, return_period: int) -> float:
        self._ensure_fitted()
        p = 1.0 / return_period  # exceedance probability
        q_shifted = stats.gamma.ppf(1.0 - p, a=self._lambda, scale=1.0 / self._alpha)
        return float(self._epsilon + q_shifted)

    def quantile_curve(self, p_grid: np.ndarray) -> np.ndarray:
        self._ensure_fitted()
        return self._epsilon + stats.gamma.ppf(
            1.0 - p_grid, a=self._lambda, scale=1.0 / self._alpha
        )

    def fitted_params(self) -> dict[str, float]:
        self._ensure_fitted()
        return {
            "epsilon": self._epsilon,
            "lambda": self._lambda,
            "alpha": self._alpha,
            "loglik": self._loglik,
        }

    # ----------------------------------------------------------- diagnostic

    def profile_likelihood(self) -> tuple[np.ndarray, np.ndarray]:
        """Return (ε_grid, log L(ε)) for diagnostic plotting.

        A flat or monotonic profile suggests Pearson III is over-parameterized
        for this series — consider a 2-parameter distribution (e.g. plain gamma
        or log-normal). The maximum should be a clear interior peak.
        """
        self._ensure_fitted()
        return self._profile_eps, self._profile_ll
