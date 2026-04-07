#!/usr/bin/env python3
"""
Fit a Log-Normal distribution (Method of Moments) to annual maximum flows (WQ)
and save Q_100 / Q_1000 estimates and fitted parameters to the database for
every station whose WQ series contains more than 30 years of data.

Results are appended to ``fitted_distributions`` and ``estimated_discharges``;
re-running the script will add duplicate rows.

Usage
-----
    uv run run_estimation_all.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

from modules.db import Database
from modules.estimation import LogNormalMoM

DB_PATH = Path(__file__).parent / "hydro.duckdb"

RETURN_PERIODS = [100, 1000]
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


def insert_fitted_distribution(
    db: Database,
    station_code: str,
    estimator: LogNormalMoM,
    series: pd.Series,
) -> None:
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


def insert_estimate(
    db: Database,
    station_code: str,
    return_period: int,
    estimator: LogNormalMoM,
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


def run_station(db: Database, station_code: str, label: str) -> None:
    series = fetch_wq(db, station_code)
    if series.empty:
        print(f"  WARNING: no WQ data for {label}, skipping.")
        return

    try:
        estimator = LogNormalMoM()
        estimator.fit(series)
    except ValueError as exc:
        print(f"  WARNING: fit failed for {label}: {exc}")
        return

    params = estimator.fitted_params()
    print(
        f"  n={int(params['n'])}  "
        f"mu_log={params['mu_log']:.4f}  "
        f"sigma_log={params['sigma_log']:.4f}"
    )

    insert_fitted_distribution(db, station_code, estimator, series)

    for t in RETURN_PERIODS:
        q = estimator.estimate(t)
        insert_estimate(db, station_code, t, estimator, q)
        print(f"    Q_{t:<4d} = {q:.1f} m³/s")


def main() -> None:
    if not DB_PATH.exists():
        print(
            f"ERROR: {DB_PATH} not found. Run raw_data_parser.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    db = Database(str(DB_PATH))
    db.create_frequency_analysis_schema()

    stations = fetch_stations(db)
    print(f"Found {len(stations)} stations with WQ series > {MIN_YEARS} years.\n")

    for i, (station_code, station_name, river_name) in enumerate(stations, 1):
        print(f"[{i}/{len(stations)}] {station_name} ({river_name})")
        run_station(db, station_code, station_name)

    db.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
