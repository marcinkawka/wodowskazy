"""
Statistical tests for hydrological time series.

Notation follows IMGW convention:
  Q = flow [m³/s]   W = water level [cm]
  WQ = annual maximum flow

Classes
-------
StatisticalTest         — abstract base class; all tests must implement run()
GrubbsBeckTest          — Grubbs-Beck outlier test (Bulletin 17B, log-space)
KruskalWallisTest       — Kruskal-Wallis stationarity test (k groups split)
WaldWolfowitzRunsTest   — Wald-Wolfowitz runs test for randomness
MannKendallTest         — Mann-Kendall monotonic trend test
SpearmanRankTest        — Spearman rank correlation with time (trend)
"""

from abc import ABC, abstractmethod

import numpy as np
from scipy import stats


class StatisticalTest(ABC):
    """Abstract base for hydrological statistical tests."""

    @abstractmethod
    def run(self, timeseries: list[float]) -> tuple[bool, list[float]]:
        """
        Run the test on a timeseries of observed values.

        Parameters
        ----------
        timeseries : list[float]
            Observed values (must contain at least 3 positive entries).

        Returns
        -------
        passed : bool
            True if the series passes the test (no outliers / hypothesis not
            rejected), False otherwise.
        outliers : list[float]
            Values identified as outliers (empty when passed=True).
        """
        ...


class GrubbsBeckTest(StatisticalTest):
    """
    Grubbs-Beck outlier detection test for flood-frequency analysis.

    The test operates in log₁₀ space as recommended by Bulletin 17B (WRC).
    Both low and high outliers are detected in a single pass.

    An outlier threshold pair (Q_L, Q_H) is defined as:
        Q_L = 10 ** (ȳ − K_n · s_y)
        Q_H = 10 ** (ȳ + K_n · s_y)

    where ȳ and s_y are the mean and standard deviation of log₁₀(Q), and
    K_n is the critical value derived from the t-distribution (Grubbs 1950):

        K_n = (n−1)/√n · √(t² / (n−2+t²))

    with t = t_{α/(2n), df=n−2}  (two-sided family-wise α).

    Parameters
    ----------
    alpha : float
        Significance level (default 0.10 = 10 %).

    result=True  — no outliers detected (series passed the test)
    result=False — one or more outliers detected
    """

    def __init__(self, alpha: float = 0.10) -> None:
        self.alpha = alpha

    def _critical_value(self, n: int) -> float:
        p = self.alpha / (2 * n)
        t_crit = float(stats.t.ppf(1.0 - p, df=n - 2))
        return (n - 1) / np.sqrt(n) * np.sqrt(t_crit**2 / (n - 2 + t_crit**2))

    def run(self, timeseries: list[float]) -> tuple[bool, list[float]]:
        data = np.array([x for x in timeseries if x > 0], dtype=float)
        if len(data) < 3:
            raise ValueError(f"Need at least 3 positive values, got {len(data)}")

        logs = np.log10(data)
        mean_log = float(logs.mean())
        std_log = float(logs.std(ddof=1))
        kn = self._critical_value(len(data))

        low_threshold = 10 ** (mean_log - kn * std_log)
        high_threshold = 10 ** (mean_log + kn * std_log)

        outliers = [
            float(x) for x in data if x < low_threshold or x > high_threshold
        ]
        return len(outliers) == 0, outliers


class KruskalWallisTest(StatisticalTest):
    """
    Kruskal-Wallis non-parametric stationarity test.

    The series is split into k roughly equal groups and tested for the null
    hypothesis that all groups are drawn from the same distribution
    (i.e. the series is stationary over time).

    Parameters
    ----------
    k     : int   Number of groups to split the series into (default 2).
    alpha : float Significance level (default 0.05).

    run() returns
    -------------
    passed  : True  — null hypothesis not rejected (series appears stationary)
              False — significant difference detected between groups
    outliers: always empty — the concept of individual outliers does not apply
              to this test; use result_notes for the p-value.
    """

    def __init__(self, k: int = 2, alpha: float = 0.05) -> None:
        if k < 2:
            raise ValueError("k must be at least 2")
        self.k = k
        self.alpha = alpha

    def run(self, timeseries: list[float]) -> tuple[bool, list[float]]:
        data = list(timeseries)
        if len(data) < self.k:
            raise ValueError(
                f"Need at least {self.k} values to form {self.k} groups, "
                f"got {len(data)}"
            )

        n = len(data)
        # Split into k groups as evenly as possible
        base, remainder = divmod(n, self.k)
        groups: list[list[float]] = []
        start = 0
        for i in range(self.k):
            end = start + base + (1 if i < remainder else 0)
            groups.append(data[start:end])
            start = end

        _, p_value = stats.kruskal(*groups)
        passed = float(p_value) >= self.alpha
        return passed, []

    def last_p_value(self, timeseries: list[float]) -> float:
        """Return the p-value for the last run (convenience helper)."""
        data = list(timeseries)
        n = len(data)
        base, remainder = divmod(n, self.k)
        groups: list[list[float]] = []
        start = 0
        for i in range(self.k):
            end = start + base + (1 if i < remainder else 0)
            groups.append(data[start:end])
            start = end
        _, p_value = stats.kruskal(*groups)
        return float(p_value)


class WaldWolfowitzRunsTest(StatisticalTest):
    """
    Wald-Wolfowitz runs test for randomness / independence.

    Values are dichotomised at the median: above → '+', below → '−',
    ties are dropped. The number of runs R is compared to the expected
    count under the null hypothesis of randomness using a normal approximation:

        E[R]   = 2·n₁·n₂/(n₁+n₂) + 1
        Var[R] = 2·n₁·n₂·(2·n₁·n₂ − n₁ − n₂) / ((n₁+n₂)²·(n₁+n₂−1))
        Z      = (R − E[R]) / √Var[R]

    Two-sided test at the given significance level.

    Parameters
    ----------
    alpha : float  Significance level (default 0.05).

    Attributes
    ----------
    p_value : float  Set after each call to run().

    result=True  — series appears random (H₀ not rejected)
    result=False — non-random structure detected
    """

    def __init__(self, alpha: float = 0.05) -> None:
        self.alpha = alpha
        self.p_value: float = float("nan")

    def run(self, timeseries: list[float]) -> tuple[bool, list[float]]:
        median = float(np.median(timeseries))
        signs = [1 if x > median else -1 for x in timeseries if x != median]

        if len(signs) < 2:
            raise ValueError("Not enough non-tie values to run the test")

        n1 = signs.count(1)
        n2 = signs.count(-1)
        n = n1 + n2

        runs = 1 + sum(
            1 for i in range(1, len(signs)) if signs[i] != signs[i - 1]
        )

        e_r = 2 * n1 * n2 / n + 1
        var_r = 2 * n1 * n2 * (2 * n1 * n2 - n) / (n * n * (n - 1))
        z = (runs - e_r) / np.sqrt(var_r)

        self.p_value = float(2 * (1 - stats.norm.cdf(abs(z))))
        return self.p_value >= self.alpha, []


class MannKendallTest(StatisticalTest):
    """
    Mann-Kendall non-parametric test for monotonic trend.

    Computes the S statistic (sum of concordant minus discordant pairs)
    and uses the normal approximation for significance:

        S     = Σ_{i<j} sign(xⱼ − xᵢ)
        Var(S) = n(n−1)(2n+5) / 18
        Z     = (S − sgn(S)) / √Var(S)

    Two-sided test at the given significance level.

    Parameters
    ----------
    alpha : float  Significance level (default 0.05).

    Attributes
    ----------
    p_value : float  Set after each call to run().

    result=True  — no significant trend (H₀ not rejected)
    result=False — significant monotonic trend detected
    """

    def __init__(self, alpha: float = 0.05) -> None:
        self.alpha = alpha
        self.p_value: float = float("nan")

    def run(self, timeseries: list[float]) -> tuple[bool, list[float]]:
        x = list(timeseries)
        n = len(x)
        if n < 3:
            raise ValueError(f"Need at least 3 values, got {n}")

        s = sum(
            int(np.sign(x[j] - x[i]))
            for i in range(n - 1)
            for j in range(i + 1, n)
        )

        var_s = n * (n - 1) * (2 * n + 5) / 18
        if s > 0:
            z = (s - 1) / np.sqrt(var_s)
        elif s < 0:
            z = (s + 1) / np.sqrt(var_s)
        else:
            z = 0.0

        self.p_value = float(2 * (1 - stats.norm.cdf(abs(z))))
        return self.p_value >= self.alpha, []


class SpearmanRankTest(StatisticalTest):
    """
    Spearman rank correlation test between the series values and time.

    Correlates each value with its temporal index (1, 2, …, n) to detect
    a monotonic trend. Uses scipy.stats.spearmanr which provides an exact
    two-sided p-value.

    Parameters
    ----------
    alpha : float  Significance level (default 0.05).

    Attributes
    ----------
    p_value     : float  Set after each call to run().
    correlation : float  Spearman ρ set after each call to run().

    result=True  — no significant rank correlation with time (no trend)
    result=False — significant monotonic trend detected
    """

    def __init__(self, alpha: float = 0.05) -> None:
        self.alpha = alpha
        self.p_value: float = float("nan")
        self.correlation: float = float("nan")

    def run(self, timeseries: list[float]) -> tuple[bool, list[float]]:
        n = len(timeseries)
        if n < 3:
            raise ValueError(f"Need at least 3 values, got {n}")

        rho, p = stats.spearmanr(timeseries, range(n))
        self.correlation = float(rho)
        self.p_value = float(p)
        return self.p_value >= self.alpha, []
