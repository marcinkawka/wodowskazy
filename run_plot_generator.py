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

import pandas as pd

from modules.db import DuckDatabase as Database
from modules.plotting import plot_distribution

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


def fetch_fitted_params(db: Database, station_code: str) -> list[dict]:
    """Return the most-recent fit per distribution type for this station/frequency.

    Each entry contains:
      ``fitted_id``        — PK of the fitted_distributions row
      ``distribution_id``  — FK into the distributions catalogue
      ``distribution_name``— human-readable name (e.g. "Log-Normal", "Gumbel")
      ``params``           — parsed distribution_params JSON dict
    """
    rows = db.con.execute(
        """
        SELECT fd.id, fd.distribution_id, d.name, fd.distribution_params
        FROM fitted_distributions fd
        JOIN distributions d ON fd.distribution_id = d.id
        WHERE fd.station_code = ? AND fd.frequency_id = ?
        ORDER BY fd.distribution_id, fd.id DESC
        """,
        [station_code, FREQUENCY_ID],
    ).fetchall()
    seen: set[int] = set()
    result: list[dict] = []
    for fitted_id, dist_id, dist_name, params_json in rows:
        if dist_id not in seen:
            seen.add(dist_id)
            result.append(
                {
                    "fitted_id": fitted_id,
                    "distribution_id": dist_id,
                    "distribution_name": dist_name,
                    "params": json.loads(params_json),
                }
            )
    return result


def fetch_ci(db: Database, fitted_distribution_id: int) -> dict | None:
    row = db.con.execute(
        "SELECT ci_data FROM ci_estimates"
        " WHERE fitted_distribution_id = ?"
        " ORDER BY id DESC LIMIT 1",
        [fitted_distribution_id],
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

    all_fitted = fetch_fitted_params(db, station_code)
    if not all_fitted:
        print(
            f"  WARNING: no fitted distribution found for {station_name}. "
            "Run run_estimation.py first."
        )
        return

    uuid = fetch_uuid(db, station_code)
    if uuid is None:
        print(f"  WARNING: station {station_code} not found in gauges_list.")
        return

    fits: list[dict] = []
    for fit in all_fitted:
        dist_name: str = fit["distribution_name"]
        print(f"  [{dist_name}] parameters for {station_name}:")
        for k, v in fit["params"].items():
            print(f"    {k}: {v:.2f}")
        fits.append({**fit, "ci": fetch_ci(db, fit["fitted_id"])})

    output_path = plot_distribution(
        station_code=station_code,
        station_name=station_name,
        river_name=river_name,
        uuid=uuid,
        wq_series=wq,
        fits=fits,
        output_dir=OUTPUT_DIR,
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
