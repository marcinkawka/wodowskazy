#!/usr/bin/env python3
"""
Fit distributions to annual maximum flows (WQ) for selected stations
and print Q_100 / Q_1000 estimates.

Stations
--------
  DĘBLIN   — Wisła,        station_code 151210120
  KŁODZKO  — Nysa Kłodzka, station_code 150160180
  WARSZAWA — Wisła,        station_code 152210010

Usage
-----
    uv run run_estimation.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

from modules.db import DuckDatabase as Database
from modules.estimation import (
    BootstrapCI,
    DischargeEstimator,
    LogNormal3pMLE,
    LogNormalMoM,
    PearsonIIIMLE,
    WeibullMLE,
)

DB_PATH = Path(__file__).parent / "hydro.duckdb"

STATIONS = [
    ("151210120", "DĘBLIN", "Wisła"),
    ("150160180", "KŁODZKO", "Nysa Kłodzka"),
    ("152210010", "WARSZAWA", "Wisła"),
]

ESTIMATOR_CLASSES: list[type[DischargeEstimator]] = [
    LogNormalMoM,
    LogNormal3pMLE,
    PearsonIIIMLE,
    WeibullMLE,
]

RETURN_PERIODS = [100, 1000]
FREQUENCY_ID = 1  # annual


def fetch_wq(db: Database, station_code: str) -> pd.Series:
    rows = db.con.execute(
        "SELECT hydro_year, WQ FROM stats_annual"
        " WHERE station_code = ? AND WQ IS NOT NULL"
        " ORDER BY hydro_year",
        [station_code],
    ).fetchall()
    years = [r[0] for r in rows]
    values = [r[1] for r in rows]
    return pd.Series(values, index=years, name="WQ")


def insert_fitted_distribution(
    db: Database,
    station_code: str,
    estimator: DischargeEstimator,
    series: pd.Series,
) -> int:
    source_info = {
        "station_code": station_code,
        "frequency_id": FREQUENCY_ID,
        "year_start": int(series.index.min()),
        "year_end": int(series.index.max()),
        "n": int(series.count()),
    }
    next_id = db.con.execute("SELECT nextval('fitted_distributions_id_seq')").fetchone()[0]
    db.con.execute(
        "INSERT INTO fitted_distributions"
        " (id, estimation_method_id, distribution_id, frequency_id,"
        "  distribution_params, station_code, source_timeseries_info)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            next_id,
            estimator.estimation_method_id,
            estimator.distribution_id,
            FREQUENCY_ID,
            json.dumps(estimator.fitted_params()),
            station_code,
            json.dumps(source_info),
        ],
    )
    return int(next_id)


def insert_ci_estimate(db: Database, fitted_distribution_id: int, ci_result: dict) -> None:  # type: ignore[type-arg]
    next_id = db.con.execute("SELECT nextval('ci_estimates_id_seq')").fetchone()[0]
    db.con.execute(
        "INSERT INTO ci_estimates (id, fitted_distribution_id, alpha, n_bootstrap, ci_data)"
        " VALUES (?, ?, ?, ?, ?)",
        [
            next_id,
            fitted_distribution_id,
            ci_result["alpha"],
            ci_result["n_bootstrap"],
            json.dumps(ci_result),
        ],
    )


def insert_estimate(
    db: Database,
    station_code: str,
    return_period: int,
    estimator: DischargeEstimator,
    value: float,
) -> None:
    notes = estimator.fitted_params()
    notes["Q_estimated_m3s"] = round(value, 3)

    next_id = db.con.execute("SELECT nextval('estimated_discharges_id_seq')").fetchone()[0]
    db.con.execute(
        "INSERT INTO estimated_discharges"
        " (id, station_code, return_period, distribution_id,"
        "  estimation_method_id, frequency_id, notes)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            next_id,
            station_code,
            return_period,
            estimator.distribution_id,
            estimator.estimation_method_id,
            FREQUENCY_ID,
            json.dumps(notes),
        ],
    )


def run_estimator(
    db: Database,
    station_code: str,
    series: pd.Series,
    estimator_cls: type[DischargeEstimator],
) -> None:
    estimator = estimator_cls()
    estimator.fit(series)
    params = estimator.fitted_params()
    params_str = ", ".join(
        f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}" for k, v in params.items()
    )
    print(f"  [{estimator_cls.__name__}] {params_str}")

    fitted_id = insert_fitted_distribution(db, station_code, estimator, series)

    for t in RETURN_PERIODS:
        q = estimator.estimate(t)
        insert_estimate(db, station_code, t, estimator, q)
        print(f"  Q_{t:<4d} = {q:.1f} m³/s")

    ci_result = BootstrapCI(n_samples=5000, alpha=0.1).compute(series, estimator_cls)
    insert_ci_estimate(db, fitted_id, ci_result)
    print(f"  CI (90%, bootstrap n={ci_result['n_valid']}) stored.")


def run_station(db: Database, station_code: str, label: str) -> None:
    series = fetch_wq(db, station_code)
    if series.empty:
        print(f"  WARNING: no WQ data for {label}, skipping.")
        return

    for estimator_cls in ESTIMATOR_CLASSES:
        run_estimator(db, station_code, series, estimator_cls)


def main() -> None:
    if not DB_PATH.exists():
        print(
            f"ERROR: {DB_PATH} not found. Run raw_data_parser.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    db = Database(str(DB_PATH))
    db.create_frequency_analysis_schema()

    for station_code, station_name, river_name in STATIONS:
        print(f"\n{station_name} ({river_name})")
        run_station(db, station_code, station_name)

    db.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
