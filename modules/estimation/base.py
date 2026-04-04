"""
Abstract base class for discharge estimation methods.

Each concrete subclass pairs a statistical distribution family with a
parameter estimation approach (e.g. Log-Normal + Method of Moments).

Workflow
--------
1. Call fit(timeseries) to estimate distribution parameters from observed data.
2. Call estimate(return_period) one or more times to obtain quantile estimates.

The distribution_id and estimation_method_id class attributes map to the
`distributions` and `estimation_methods` catalogue tables in the database.
"""

from abc import ABC, abstractmethod

import pandas as pd


class DischargeEstimator(ABC):
    """Abstract base for flood-frequency discharge estimators."""

    #: FK → distributions.id  (must be set by every subclass)
    distribution_id: int
    #: FK → estimation_methods.id  (must be set by every subclass)
    estimation_method_id: int

    @abstractmethod
    def fit(self, timeseries: pd.Series) -> None:
        """
        Estimate distribution parameters from an observed timeseries.

        Parameters
        ----------
        timeseries : pd.Series
            Annual (or seasonal) maximum discharges [m³/s].
            Must contain at least 3 positive values.
            The index is typically hydro_year integers.
        """
        ...

    @abstractmethod
    def estimate(self, return_period: int) -> float:
        """
        Return the discharge estimate for a given return period.

        Parameters
        ----------
        return_period : int
            Return period in years (e.g. 100, 1000).
            fit() must have been called before this method.

        Returns
        -------
        float
            Estimated discharge Q_T [m³/s].
        """
        ...

    @abstractmethod
    def fitted_params(self) -> dict[str, float]:
        """
        Return the fitted distribution parameters as a plain dict.

        Used to populate the `notes` JSON column in estimated_discharges.
        fit() must have been called first.
        """
        ...
