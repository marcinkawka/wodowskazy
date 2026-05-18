#!/usr/bin/env python3
"""
Evaluate goodness-of-fit for estimated distributions using the lambda-Kolmogorov test.

For each station the script:
  1. Fetches the annual maximum flow series (WQ) from ``stats_annual``.
  2. Fetches the most recent Pearson III fit from ``fitted_distributions``.
  3. Runs the lambda-Kolmogorov test:
       D = max |F_empirical(x) − F_Pearson_III(x)|
       λ = D · √N
     Passes if λ < 1.36  (critical value at α = 5%, equivalent to D < 1.36/√N).
  4. Persists results to ``dist_test_results`` (append-only).

Stations
--------
  DĘBLIN   — Wisła,        station_code 151210120
  KŁODZKO  — Nysa Kłodzka, station_code 150160180
  WARSZAWA — Wisła,        station_code 152210010

Usage
-----
    uv run run_stat_distribution_tests.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from modules.db import DuckDatabase as Database

DB_PATH = Path(__file__).parent / "hydro.duckdb"

STATIONS = [
    ("151210120", "DĘBLIN", "Wisła"),
    ("150160180", "KŁODZKO", "Nysa Kłodzka"),
    ("152210010", "WARSZAWA", "Wisła"),
]

FREQUENCY_ID = 1  # annual
PEARSON_III_DIST_ID = 3
LAMBDA_KOLMOGOROV_TEST_ID = 7
CRITICAL_LAMBDA = 1.36  # KS critical value at α = 5%


def fetch_wq(db: Database, station_code: str) -> pd.Series:
    rows = db.con.execute(
        "SELECT hydro_year, WQ FROM stats_annual"
        " WHERE station_code = ? AND WQ IS NOT NULL"
        " ORDER BY hydro_year",
        [station_code],
    ).fetchall()
    return pd.Series([r[1] for r in rows], index=[r[0] for r in rows], name="WQ")


def fetch_pearsoniii_fit(db: Database, station_code: str) -> tuple[int, dict] | None:
    """Return (fitted_distribution_id, params) for the most recent Pearson III annual fit."""
    row = db.con.execute(
        "SELECT id, distribution_params FROM fitted_distributions"
        " WHERE station_code = ? AND distribution_id = ? AND frequency_id = ?"
        " ORDER BY id DESC LIMIT 1",
        [station_code, PEARSON_III_DIST_ID, FREQUENCY_ID],
    ).fetchone()
    if row is None:
        return None
    return int(row[0]), json.loads(row[1])


def run_lambda_kolmogorov(db: Database, station_code: str, station_name: str) -> None:
    wq = fetch_wq(db, station_code)
    if wq.empty:
        print(f"  WARNING: no WQ data for {station_name}, skipping.")
        return

    fit = fetch_pearsoniii_fit(db, station_code)
    if fit is None:
        print(
            f"  WARNING: no Pearson III fit found for {station_name}. "
            "Run run_estimation.py first."
        )
        return

    fitted_id, params = fit
    epsilon: float = params["epsilon"]
    lam: float = params["lambda"]
    alpha: float = params["alpha"]

    n = len(wq)
    data = wq.to_numpy(dtype=float)

    def cdf(x: np.ndarray) -> np.ndarray:
        return stats.gamma.cdf(x - epsilon, a=lam, scale=1.0 / alpha)  # type: ignore[return-value]

    ks_stat, _ = stats.ks_1samp(data, cdf)
    lambda_stat = float(ks_stat) * np.sqrt(n)
    passed = bool(lambda_stat < CRITICAL_LAMBDA)

    notes = (
        f"n={n}, D={ks_stat:.4f}, λ={lambda_stat:.4f}, "
        f"critical λ={CRITICAL_LAMBDA} (α=5%)"
    )

    next_id = db.con.execute("SELECT nextval('dist_test_results_id_seq')").fetchone()[0]
    db.con.execute(
        "INSERT INTO dist_test_results (id, fitted_distribution_id, test_id, result_notes, result)"
        " VALUES (?, ?, ?, ?, ?)",
        [next_id, fitted_id, LAMBDA_KOLMOGOROV_TEST_ID, notes, passed],
    )

    status = "PASSED" if passed else "FAILED"
    print(f"  Lambda-Kolmogorov [{status}]  {notes}")


def main() -> None:
    if not DB_PATH.exists():
        print(
            f"ERROR: {DB_PATH} not found. Run raw_data_parser.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    db = Database(str(DB_PATH))
    db.create_stat_tests_schema()        # ensures stat_tests catalogue exists
    db.create_frequency_analysis_schema()  # ensures fitted_distributions exists
    db.create_dist_tests_schema()        # seeds Lambda-Kolmogorov, creates dist_test_results

    for station_code, station_name, river_name in STATIONS:
        print(f"\n{station_name} ({river_name})")
        run_lambda_kolmogorov(db, station_code, station_name)

    db.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
