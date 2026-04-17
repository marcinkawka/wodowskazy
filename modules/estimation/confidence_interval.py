"""
Bootstrap confidence intervals for fitted discharge quantile curves.

For a given observed WQ timeseries and a DischargeEstimator subclass the
bootstrap procedure:

  1. Draws ``n_samples`` resamples (with replacement) of size n from the
     positive values in the series.
  2. Fits a fresh estimator instance to each resample.
  3. Evaluates the Q(p) curve at every probability in ``p_grid`` via
     ``DischargeEstimator.quantile_curve()``.
  4. Returns the alpha/2 and (1-alpha/2) quantile bands across all
     successfully fitted resamples.

The result dict is intended to be serialised directly to JSON and stored in
the ``ci_estimates.ci_data`` column.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .base import DischargeEstimator

# Standard probability grid used for storage and plotting (200 points).
# Matches the range used for the theoretical curve in modules/plotting.py.
CI_P_GRID: np.ndarray = np.linspace(0.0005, 0.9995, 200)


class BootstrapCI:
    """Bootstrap confidence intervals for a Q(p) quantile curve."""

    def __init__(self, n_samples: int = 5000, alpha: float = 0.1) -> None:
        """
        Parameters
        ----------
        n_samples : int
            Number of bootstrap resamples.  Default: 5000.
        alpha : float
            Two-sided significance level.  The CI spans the
            [alpha/2, 1-alpha/2] quantile range.  Default: 0.1 (90 % CI).
        """
        if not 0 < alpha < 1:
            raise ValueError(f"alpha must be in (0, 1), got {alpha}")
        self.n_samples = n_samples
        self.alpha = alpha

    def compute(
        self,
        timeseries: pd.Series,
        estimator_cls: type[DischargeEstimator],
        p_grid: np.ndarray = CI_P_GRID,
    ) -> dict[str, Any]:
        """
        Compute the bootstrap CI for the Q(p) curve.

        Parameters
        ----------
        timeseries : pd.Series
            Observed annual maximum flow series [m³/s].
            Non-positive values are silently dropped before resampling.
        estimator_cls : type[DischargeEstimator]
            Estimator class to instantiate and fit on each resample.
            Must implement ``quantile_curve()``.
        p_grid : np.ndarray
            Exceedance probability grid in (0, 1) at which Q is evaluated.
            Defaults to ``CI_P_GRID`` (200 uniformly-spaced points).

        Returns
        -------
        dict with keys:
            probabilities  list[float]   — p_grid echoed back
            q_lower        list[float]   — alpha/2 quantile band
            q_upper        list[float]   — (1-alpha/2) quantile band
            alpha          float         — significance level used
            n_bootstrap    int           — n_samples requested
            n_valid        int           — resamples that converged
        """
        data = timeseries[timeseries > 0].to_numpy(dtype=float)
        n = len(data)
        if n < 3:
            raise ValueError(f"Need at least 3 positive values, got {n}")

        rng = np.random.default_rng()
        curves = np.empty((self.n_samples, len(p_grid)))

        for i in range(self.n_samples):
            resample = pd.Series(rng.choice(data, size=n, replace=True))
            est = estimator_cls()
            try:
                est.fit(resample)
                curves[i] = est.quantile_curve(p_grid)
            except (ValueError, RuntimeError):
                curves[i] = np.nan

        valid_mask = ~np.any(np.isnan(curves), axis=1)
        valid_curves = curves[valid_mask]

        q_lower = np.quantile(valid_curves, self.alpha / 2, axis=0)
        q_upper = np.quantile(valid_curves, 1.0 - self.alpha / 2, axis=0)

        return {
            "probabilities": p_grid.tolist(),
            "q_lower": q_lower.tolist(),
            "q_upper": q_upper.tolist(),
            "alpha": self.alpha,
            "n_bootstrap": self.n_samples,
            "n_valid": int(valid_mask.sum()),
        }
