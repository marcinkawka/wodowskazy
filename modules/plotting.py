"""
Probability plots for hydrological frequency analysis.

Polish hydrology convention:
  X axis — exceedance probability p [%] on a probit (normal probability)
            scale, increasing from right to left (high probability on the
            left, rare events on the right).
  Y axis — discharge Q [m³/s], linear scale, increasing upward.

Empirical plotting positions follow the Hazen (mean-rank) formula:
    p_i = (n − m + 0.5) / n
where m is the rank of observation sorted in ascending order (m=1 smallest).

For a Log-Normal distribution (ln Q ~ N(μ, σ²)), the T-year quantile at
exceedance probability p = 1/T is:
    Q(p) = exp(μ + σ · Φ⁻¹(1 − p)) = exp(μ − σ · z_p)
where z_p = Φ⁻¹(p) is the standard normal quantile used as the x-coordinate.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from scipy import stats

# Standard exceedance probability ticks used in Polish hydrology
_P_TICKS = [0.001, 0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 0.80, 0.90, 0.95, 0.99]
_P_LABELS = ["0.1%", "0.5%", "1%", "2%", "5%", "10%", "20%", "50%", "80%", "90%", "95%", "99%"]

# Vertical reference lines highlighting key return periods
_V_LINE_PROBS = [0.01, 0.002, 0.001]  # 1%, 0.2%, 0.1%
_V_LINE_LABELS = ["p=1%\n(T=100)", "p=0.2%\n(T=500)", "p=0.1%\n(T=1000)"]

# Color cycle for theoretical curves (index = position in fits list)
_CURVE_COLORS = ["firebrick", "darkorange", "forestgreen", "purple", "saddlebrown"]


def _mean_rank_exceedance(n: int) -> np.ndarray:
    """
    Hazen (mean-rank) exceedance plotting positions for n observations
    sorted ascending.

        p_m = (n − m + 0.5) / n

    where m=1 is the smallest value (highest exceedance, most frequent).
    """
    ranks = np.arange(1, n + 1)
    return (n - ranks + 0.5) / n


def _plot_lognormal_curve(
    ax: plt.Axes,
    params: dict,
    ci: dict | None,
    color: str,
) -> None:
    """Add a Log-Normal theoretical curve and optional CI band to *ax*."""
    mu_log: float = params["mu_log"]
    sigma_log: float = params["sigma_log"]

    p_curve = np.linspace(0.0005, 0.9995, 1000)
    z_curve = stats.norm.ppf(p_curve)
    q_curve = np.exp(mu_log - sigma_log * z_curve)

    ax.plot(
        z_curve,
        q_curve,
        linestyle="-",
        linewidth=2.0,
        color=color,
        label="Log-Normal (MoM)",
        zorder=2,
    )

    if ci:
        z_ci = stats.norm.ppf(np.array(ci["probabilities"]))
        ax.fill_between(
            z_ci,
            np.array(ci["q_lower"]),
            np.array(ci["q_upper"]),
            alpha=0.20,
            color=color,
            label="_nolegend_",
            zorder=1,
        )


def _plot_pearsoniii_curve(
    ax: plt.Axes,
    params: dict,
    ci: dict | None,
    color: str,
) -> None:
    """Add a Pearson III theoretical curve and optional CI band to *ax*."""
    epsilon: float = params["epsilon"]
    lam: float = params["lambda"]
    alpha: float = params["alpha"]

    p_curve = np.linspace(0.0005, 0.9995, 1000)
    z_curve = stats.norm.ppf(p_curve)
    q_curve = epsilon + stats.gamma.ppf(1.0 - p_curve, a=lam, scale=1.0 / alpha)

    ax.plot(
        z_curve,
        q_curve,
        linestyle="-",
        linewidth=2.0,
        color=color,
        label="Pearson III (MLE)",
        zorder=2,
    )

    if ci:
        z_ci = stats.norm.ppf(np.array(ci["probabilities"]))
        ax.fill_between(
            z_ci,
            np.array(ci["q_lower"]),
            np.array(ci["q_upper"]),
            alpha=0.20,
            color=color,
            label="_nolegend_",
            zorder=1,
        )


def _plot_lognormal3p_curve(
    ax: plt.Axes,
    params: dict,
    ci: dict | None,
    color: str,
) -> None:
    """Add a 3-parameter Log-Normal (MLE) theoretical curve and optional CI band to *ax*."""
    epsilon: float = params["epsilon"]
    mu: float = params["mu"]
    sigma: float = params["sigma"]

    p_curve = np.linspace(0.0005, 0.9995, 1000)
    z_curve = stats.norm.ppf(p_curve)
    q_curve = epsilon + np.exp(mu - sigma * z_curve)

    ax.plot(
        z_curve,
        q_curve,
        linestyle="-",
        linewidth=2.0,
        color=color,
        label="Log-Normal 3p (MLE)",
        zorder=2,
    )

    if ci:
        z_ci = stats.norm.ppf(np.array(ci["probabilities"]))
        ax.fill_between(
            z_ci,
            np.array(ci["q_lower"]),
            np.array(ci["q_upper"]),
            alpha=0.20,
            color=color,
            label="_nolegend_",
            zorder=1,
        )


def _plot_weibull_curve(
    ax: plt.Axes,
    params: dict,
    ci: dict | None,
    color: str,
) -> None:
    """Add a Weibull (MLE) theoretical curve and optional CI band to *ax*."""
    epsilon: float = params["epsilon"]
    alpha: float = params["alpha"]
    beta: float = params["beta"]

    p_curve = np.linspace(0.0005, 0.9995, 1000)
    z_curve = stats.norm.ppf(p_curve)
    q_curve = epsilon + (-np.log(p_curve)) ** (1.0 / beta) / alpha

    ax.plot(
        z_curve,
        q_curve,
        linestyle="-",
        linewidth=2.0,
        color=color,
        label="Weibull (MLE)",
        zorder=2,
    )

    if ci:
        z_ci = stats.norm.ppf(np.array(ci["probabilities"]))
        ax.fill_between(
            z_ci,
            np.array(ci["q_lower"]),
            np.array(ci["q_upper"]),
            alpha=0.20,
            color=color,
            label="_nolegend_",
            zorder=1,
        )


def plot_distribution(
    station_code: str,
    station_name: str,
    river_name: str,
    uuid: str,
    wq_series: pd.Series,
    fits: list[dict],
    output_dir: Path,
) -> Path:
    """
    Generate a probability plot with one theoretical curve per entry in *fits*.

    All distributions share a single canvas so their quantile lines can be
    compared directly against the empirical data.

    Parameters
    ----------
    fits : list[dict]
        Each entry must contain:
          ``distribution_name`` — matches the ``distributions.name`` catalogue value
          ``params``            — parsed ``fitted_distributions.distribution_params`` JSON
          ``ci``                — parsed ``ci_estimates.ci_data`` JSON, or ``None``

    Returns
    -------
    Path
        Full path of the saved PNG (``output_dir / f"{uuid}.png"``).
    """
    sorted_wq = wq_series.dropna().sort_values()
    n = len(sorted_wq)
    p_emp = _mean_rank_exceedance(n)
    z_emp = stats.norm.ppf(p_emp)

    wwq_value = float(sorted_wq.iloc[-1])
    wwq_year = int(sorted_wq.index[-1])
    wwq_z = float(z_emp[-1])

    plt.style.use("ggplot")
    fig, ax = plt.subplots(figsize=(13, 7))

    # Empirical: thin polyline + markers
    ax.plot(
        z_emp,
        sorted_wq.to_numpy(),
        linestyle="-",
        linewidth=0.8,
        marker="o",
        markersize=4,
        color="steelblue",
        label="Observed annual maximum flow WQ (Hazen positions)",
        zorder=3,
    )

    # Theoretical curves — one per fit
    for i, fit in enumerate(fits):
        dist_name: str = fit["distribution_name"]
        method_id: int = fit.get("estimation_method_id", 0)
        color = _CURVE_COLORS[i % len(_CURVE_COLORS)]

        if dist_name == "Log-Normal" and method_id != 2:
            _plot_lognormal_curve(ax, fit["params"], fit.get("ci"), color)
        elif dist_name == "Log-Normal" and method_id == 2:
            _plot_lognormal3p_curve(ax, fit["params"], fit.get("ci"), color)
        elif dist_name == "Pearson III":
            _plot_pearsoniii_curve(ax, fit["params"], fit.get("ci"), color)
        elif dist_name == "Weibull":
            _plot_weibull_curve(ax, fit["params"], fit.get("ci"), color)
        else:
            print(f"  [{dist_name}] plotting not yet implemented, skipping.")

    # Vertical reference lines at 1%, 0.2%, 0.1%
    for p_vl, lbl in zip(_V_LINE_PROBS, _V_LINE_LABELS, strict=False):
        z_vl = stats.norm.ppf(p_vl)
        ax.axvline(x=z_vl, color="dimgray", linestyle=":", linewidth=1.1, alpha=0.75, zorder=1)
        ax.text(
            z_vl,
            0.99,
            lbl,
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=7.5,
            color="dimgray",
        )

    # WWQ annotation
    ax.annotate(
        f"WWQ = {wwq_value:.0f} m³/s\n(year {wwq_year})",
        xy=(wwq_z, wwq_value),
        xytext=(-55, -30),
        textcoords="offset points",
        fontsize=9,
        color="darkgreen",
        arrowprops=dict(arrowstyle="->", color="darkgreen", lw=1.2),
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="darkgreen", alpha=0.85),
        zorder=5,
    )

    ax.set_ylabel("Discharge Q  [m³/s]", fontsize=11)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}".replace(",", " ")))

    z_ticks = [stats.norm.ppf(p) for p in _P_TICKS]
    ax.set_xticks(z_ticks)
    ax.set_xticklabels(_P_LABELS)
    ax.invert_xaxis()
    ax.set_xlabel("Exceedance probability  p  [%]", fontsize=11)

    ax.xaxis.grid(True, which="major", linestyle="--", linewidth=0.6, alpha=0.7)
    ax.yaxis.grid(True, which="major", linestyle="--", linewidth=0.6, alpha=0.7)

    ax.set_title(
        f"{station_name}  ·  {river_name}  ·  code {station_code}\n"
        "Annual maximum flow — probability plot",
        fontsize=12,
        fontweight="bold",
    )
    ax.legend(loc="upper left", fontsize=10)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{uuid}.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path
