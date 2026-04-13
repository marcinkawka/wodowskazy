#!/usr/bin/env python3
"""
Generate Log-Normal probability plots for every station whose WQ series
contains more than 30 years of data and has a fitted distribution stored in
``fitted_distributions``.

Run ``run_estimation_all.py`` first to populate the fitted parameters.

For each qualifying station the script:
  1. Fetches the annual WQ series from ``stats_annual``.
  2. Fetches the most recent fitted Log-Normal parameters from
     ``fitted_distributions`` (annual frequency).
  3. Fetches the station UUID from ``gauges_list``.
  4. Calls ``modules.plotting.probability_plot()``.
  5. Saves the PNG to ``./output/<uuid>.png``.

Usage
-----
    uv run run_plot_generator_all.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from modules.db import Database
from modules.plotting import probability_plot

DB_PATH = Path(__file__).parent / "hydro.duckdb"
OUTPUT_DIR = Path(__file__).parent / "output"

FREQUENCY_ID = 1  # annual
MIN_YEARS = 30


def fetch_stations(db: Database) -> list[tuple[str, str, str]]:
    """Return all stations with more than MIN_YEARS non-null WQ observations."""
    rows = db.con.execute(
        """
        SELECT g.station_code, g.station_name, g.river_name
        FROM gauges_list g
        JOIN (
            SELECT station_code
            FROM stats_annual
            WHERE WQ IS NOT NULL
            GROUP BY station_code
            HAVING COUNT(*) > ?
        ) t ON g.station_code = t.station_code
        ORDER BY g.station_name
        """,
        [MIN_YEARS],
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


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
            f"  WARNING: no fitted distribution for {station_name}. "
            "Run run_estimation_all.py first."
        )
        return

    uuid = fetch_uuid(db, station_code)
    if uuid is None:
        print(f"  WARNING: station {station_code} not found in gauges_list.")
        return

    output_path = probability_plot(
        station_code=station_code,
        station_name=station_name,
        river_name=river_name,
        uuid=uuid,
        wq_series=wq,
        mu_log=params["mu_log"],
        sigma_log=params["sigma_log"],
        output_dir=OUTPUT_DIR,
    )
    print(f"  Saved → {output_path.name}")


def main() -> None:
    if not DB_PATH.exists():
        print(
            f"ERROR: {DB_PATH} not found. Run raw_data_parser.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    db = Database(str(DB_PATH))
    db.create_schema()  # ensures uuid column exists (migration-safe)
    db.create_frequency_analysis_schema()  # ensures ci_estimates table exists

    stations = fetch_stations(db)
    print(f"Found {len(stations)} stations with WQ series > {MIN_YEARS} years.\n")

    skipped = 0
    for i, (station_code, station_name, river_name) in enumerate(stations, 1):
        print(f"[{i}/{len(stations)}] {station_name} ({river_name})", end="  ")
        wq = fetch_wq(db, station_code)
        params = fetch_fitted_params(db, station_code)
        uuid = fetch_uuid(db, station_code)

        if wq.empty or params is None or uuid is None:
            reason = (
                "no WQ data"
                if wq.empty
                else "no fitted params — run run_estimation_all.py first"
                if params is None
                else "not in gauges_list"
            )
            print(f"SKIPPED ({reason})")
            skipped += 1
            continue

        ci = fetch_ci(db, station_code)
        output_path = probability_plot(
            station_code=station_code,
            station_name=station_name,
            river_name=river_name,
            uuid=uuid,
            wq_series=wq,
            mu_log=params["mu_log"],
            sigma_log=params["sigma_log"],
            output_dir=OUTPUT_DIR,
            ci_lower=np.array(ci["q_lower"]) if ci else None,
            ci_upper=np.array(ci["q_upper"]) if ci else None,
            ci_p_grid=np.array(ci["probabilities"]) if ci else None,
            ci_alpha=float(ci["alpha"]) if ci else 0.1,
        )
        print(f"→ {output_path.name}")

    db.close()
    print(f"\nDone. {len(stations) - skipped} plots saved, {skipped} skipped.")


if __name__ == "__main__":
    main()
