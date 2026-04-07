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
import numpy as np
import pandas as pd
from scipy import stats

# Standard exceedance probability ticks used in Polish hydrology
_P_TICKS = [0.001, 0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 0.80, 0.90, 0.95, 0.99]
_P_LABELS = ["0.1%", "0.5%", "1%", "2%", "5%", "10%", "20%", "50%", "80%", "90%", "95%", "99%"]

# Vertical reference lines highlighting key return periods
_V_LINE_PROBS = [0.01, 0.002, 0.001]  # 1%, 0.2%, 0.1%
_V_LINE_LABELS = ["p=1%\n(T=100)", "p=0.2%\n(T=500)", "p=0.1%\n(T=1000)"]


def _mean_rank_exceedance(n: int) -> np.ndarray:
    """
    Hazen (mean-rank) exceedance plotting positions for n observations
    sorted ascending.

        p_m = (n − m + 0.5) / n

    where m=1 is the smallest value (highest exceedance, most frequent).
    """
    ranks = np.arange(1, n + 1)
    return (n - ranks + 0.5) / n


def probability_plot(
    station_code: str,
    station_name: str,
    river_name: str,
    uuid: str,
    wq_series: pd.Series,
    mu_log: float,
    sigma_log: float,
    output_dir: Path,
) -> Path:
    """
    Generate a Log-Normal probability plot and save it as a PNG.

    Parameters
    ----------
    station_code : str
        IMGW station code — shown in the title.
    station_name : str
        Human-readable station name — shown in the title.
    river_name : str
        River name — shown in the title.
    uuid : str
        Station UUID from ``gauges_list``; used as the output filename.
    wq_series : pd.Series
        Annual maximum flows [m³/s] indexed by hydro_year.
    mu_log : float
        Fitted Log-Normal parameter μ = mean(ln Q).
    sigma_log : float
        Fitted Log-Normal parameter σ = std(ln Q).
    output_dir : Path
        Directory to save the PNG; created if it does not exist.

    Returns
    -------
    Path
        Full path of the saved PNG file (``output_dir / f"{uuid}.png"``).
    """
    # --- Empirical data (index = hydro_year preserved for annotation) ----------
    sorted_wq = wq_series.dropna().sort_values()  # ascending, index = hydro_year
    n = len(sorted_wq)
    p_emp = _mean_rank_exceedance(n)  # Hazen exceedance probabilities
    z_emp = stats.norm.ppf(p_emp)  # probit x-coordinates

    # WWQ: the maximum observed value and the year it occurred
    wwq_value = float(sorted_wq.iloc[-1])
    wwq_year = int(sorted_wq.index[-1])
    wwq_z = float(z_emp[-1])

    # --- Theoretical Log-Normal curve -----------------------------------------
    p_curve = np.linspace(0.0005, 0.9995, 1000)
    z_curve = stats.norm.ppf(p_curve)
    q_curve = np.exp(mu_log - sigma_log * z_curve)  # Q(p) = exp(μ − σ·z_p)

    # --- Figure ---------------------------------------------------------------
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

    # Theoretical: smooth lognormal curve
    ax.plot(
        z_curve,
        q_curve,
        linestyle="-",
        linewidth=2.0,
        color="firebrick",
        label=f"Log-Normal (MoM):  μ={mu_log:.3f},  σ={sigma_log:.3f}",
        zorder=2,
    )

    # --- Vertical reference lines at 1%, 0.2%, 0.1% --------------------------
    for p_vl, lbl in zip(_V_LINE_PROBS, _V_LINE_LABELS, strict=False):
        z_vl = stats.norm.ppf(p_vl)
        ax.axvline(x=z_vl, color="dimgray", linestyle=":", linewidth=1.1, alpha=0.75, zorder=1)
        # Label at top of the axis (y in axes coords via xaxis_transform)
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

    # --- WWQ annotation -------------------------------------------------------
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

    # --- Y axis: linear scale -------------------------------------------------
    ax.set_ylabel("Discharge Q  [m³/s]", fontsize=11)

    # --- X axis: probit scale, inverted, percentage labels --------------------
    z_ticks = [stats.norm.ppf(p) for p in _P_TICKS]
    ax.set_xticks(z_ticks)
    ax.set_xticklabels(_P_LABELS)
    ax.invert_xaxis()
    ax.set_xlabel("Exceedance probability  p  [%]", fontsize=11)

    ax.xaxis.grid(True, which="major", linestyle="--", linewidth=0.6, alpha=0.7)
    ax.yaxis.grid(True, which="major", linestyle="--", linewidth=0.6, alpha=0.7)

    ax.set_title(
        f"{station_name}  ·  {river_name}  ·  code {station_code}\n"
        "Annual maximum flow — Log-Normal probability plot",
        fontsize=12,
        fontweight="bold",
    )
    ax.legend(loc="upper right", fontsize=10)

    # --- Save -----------------------------------------------------------------
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{uuid}.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path
