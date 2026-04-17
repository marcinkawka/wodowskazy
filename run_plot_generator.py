#!/usr/bin/env python3
"""
Generate Log-Normal probability plots for selected stations.

For each station the script:
  1. Fetches the annual maximum flow series (WQ) from ``stats_annual``.
  2. Fetches the most recent fitted Log-Normal parameters from
     ``fitted_distributions`` (annual frequency).
  3. Fetches the station UUID from ``gauges_list``.
  4. Calls ``modules.plotting.probability_plot()`` to render the figure.
  5. Saves the PNG to ``./output/<uuid>.png``.

Stations
--------
  DĘBLIN   — Wisła,        station_code 151210120
  KŁODZKO  — Nysa Kłodzka, station_code 150160180
  WARSZAWA — Wisła,        station_code 152210010

Usage
-----
    uv run run_plot_generator.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from modules.db import DuckDatabase as Database
from modules.plotting import probability_plot

DB_PATH = Path(__file__).parent / "hydro.duckdb"
OUTPUT_DIR = Path(__file__).parent / "output"

STATIONS = [
    ("151210120", "DĘBLIN", "Wisła"),
    ("150160180", "KŁODZKO", "Nysa Kłodzka"),
    ("152210010", "WARSZAWA", "Wisła"),
]

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


def fetch_fitted_params(db: Database, station_code: str) -> dict | None:
    row = db.con.execute(
        "SELECT distribution_params FROM fitted_distributions"
        " WHERE station_code = ? AND frequency_id = ?"
        " ORDER BY id DESC LIMIT 1",
        [station_code, FREQUENCY_ID],
    ).fetchone()
    if row is None:
        return None
    return json.loads(row[0])


def fetch_ci(db: Database, station_code: str) -> dict | None:
    row = db.con.execute(
        "SELECT c.ci_data FROM ci_estimates c"
        " JOIN fitted_distributions fd ON c.fitted_distribution_id = fd.id"
        " WHERE fd.station_code = ? AND fd.frequency_id = ?"
        " ORDER BY fd.id DESC LIMIT 1",
        [station_code, FREQUENCY_ID],
    ).fetchone()
    if row is None:
        return None
    return json.loads(row[0])


def fetch_uuid(db: Database, station_code: str) -> str | None:
    row = db.con.execute(
        "SELECT uuid FROM gauges_list WHERE station_code = ?",
        [station_code],
    ).fetchone()
    return str(row[0]) if row else None


def run_station(
    db: Database,
    station_code: str,
    station_name: str,
    river_name: str,
) -> None:
    wq = fetch_wq(db, station_code)
    if wq.empty:
        print(f"  WARNING: no WQ data for {station_name}, skipping.")
        return

    params = fetch_fitted_params(db, station_code)
    if params is None:
        print(
            f"  WARNING: no fitted distribution found for {station_name}. "
            "Run run_estimation.py first."
        )
        return

    uuid = fetch_uuid(db, station_code)
    if uuid is None:
        print(f"  WARNING: station {station_code} not found in gauges_list.")
        return

    ci = fetch_ci(db, station_code)
    ci_lower = np.array(ci["q_lower"]) if ci else None
    ci_upper = np.array(ci["q_upper"]) if ci else None
    ci_p_grid = np.array(ci["probabilities"]) if ci else None
    ci_alpha = float(ci["alpha"]) if ci else 0.1

    output_path = probability_plot(
        station_code=station_code,
        station_name=station_name,
        river_name=river_name,
        uuid=uuid,
        wq_series=wq,
        mu_log=params["mu_log"],
        sigma_log=params["sigma_log"],
        output_dir=OUTPUT_DIR,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_p_grid=ci_p_grid,
        ci_alpha=ci_alpha,
    )
    print(f"  Saved → {output_path}")


def main() -> None:
    if not DB_PATH.exists():
        print(
            f"ERROR: {DB_PATH} not found. Run raw_data_parser.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    db = Database(str(DB_PATH))
    db.create_schema()  # ensures uuid column exists (migration-safe)
    db.create_frequency_analysis_schema()  # ensures fitted_distributions table exists

    for station_code, station_name, river_name in STATIONS:
        print(f"\n{station_name} ({river_name})")
        run_station(db, station_code, station_name, river_name)

    db.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
