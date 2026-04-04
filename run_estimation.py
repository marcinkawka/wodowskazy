#!/usr/bin/env python3
"""
Fit a Log-Normal distribution (Method of Moments) to annual maximum flows (WQ)
for selected stations and save Q_100 / Q_1000 estimates to the database.

Stations
--------
  DĘBLIN   — Wisła,        station_code 151210120
  KŁODZKO  — Nysa Kłodzka, station_code 150160180

Usage
-----
    uv run run_estimation.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

from modules.db import Database
from modules.estimation import LogNormalMoM

DB_PATH = Path(__file__).parent / "hydro.duckdb"

STATIONS = [
    ("151210120", "DĘBLIN", "Wisła"),
    ("150160180", "KŁODZKO", "Nysa Kłodzka"),
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


def insert_estimate(
    db: Database,
    station_code: str,
    return_period: int,
    estimator: LogNormalMoM,
    value: float,
) -> None:
    notes = estimator.fitted_params()
    notes["Q_estimated_m3s"] = round(value, 3)

    next_id = db.con.execute(
        "SELECT nextval('estimated_discharges_id_seq')"
    ).fetchone()[0]
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


def run_station(db: Database, station_code: str, label: str) -> None:
    series = fetch_wq(db, station_code)
    if series.empty:
        print(f"  WARNING: no WQ data for {label}, skipping.")
        return

    estimator = LogNormalMoM()
    estimator.fit(series)
    params = estimator.fitted_params()
    print(
        f"  Fitted Log-Normal MoM: "
        f"mu_log={params['mu_log']:.4f}, "
        f"sigma_log={params['sigma_log']:.4f}, "
        f"n={int(params['n'])}"
    )

    for t in RETURN_PERIODS:
        q = estimator.estimate(t)
        insert_estimate(db, station_code, t, estimator, q)
        print(f"  Q_{t:<4d} = {q:.1f} m³/s")


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
