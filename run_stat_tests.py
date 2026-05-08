#!/usr/bin/env python3
"""
Run Grubbs-Beck outlier test and Kruskal-Wallis stationarity test on annual
maximum flows (WQ) for selected stations and persist results to the database.

Stations tested (default)
-------------------------
  DĘBLIN   — Wisła,        station_code 151210120
  KŁODZKO  — Nysa Kłodzka, station_code 150160180
  WARSZAWA — Wisła,        station_code 152210010

Usage
-----
    uv run run_stat_tests.py           # 3 example stations
    uv run run_stat_tests.py --all     # all stations with WQ series > 30 years
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from modules.db import DuckDatabase as Database
from modules.stat_tests import (
    GrubbsBeckTest,
    KruskalWallisTest,
    MannKendallTest,
    SpearmanRankTest,
    WaldWolfowitzRunsTest,
)

DB_PATH = Path(__file__).parent / "hydro.duckdb"
MIN_YEARS = 30

STATIONS = [
    ("151210120", "DĘBLIN", "Wisła"),
    ("150160180", "KŁODZKO", "Nysa Kłodzka"),
    ("152210010", "WARSZAWA", "Wisła"),
]

GRUBBS_BECK_TEST_ID = 1
KRUSKAL_WALLIS_TEST_ID = 2
WALD_WOLFOWITZ_TEST_ID = 4
MANN_KENDALL_TEST_ID = 5
SPEARMAN_RANK_TEST_ID = 6
SERIES_TYPE = "WQ_annual"


def fetch_all_stations(db: Database) -> list[tuple[str, str, str]]:
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


def insert_result(
    db: Database,
    series_type: str,
    station_code: str,
    test_id: int,
    period_start: int,
    period_end: int,
    notes: str,
    result: bool,
) -> None:
    next_id = db.con.execute("SELECT nextval('stat_test_results_id_seq')").fetchone()[0]
    db.con.execute(
        "INSERT INTO stat_test_results"
        " (id, series_type, station_code, test_id,"
        "  period_start, period_end, result_notes, result)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [next_id, series_type, station_code, test_id, period_start, period_end, notes, result],
    )


def run_grubbs_beck(db: Database, station_code: str, label: str) -> None:
    series = fetch_wq(db, station_code)
    if series.empty:
        print(f"  WARNING: no WQ data for {label}, skipping Grubbs-Beck.")
        return

    test = GrubbsBeckTest(alpha=0.10)
    passed, outlier_labels = test.run(series)

    if passed:
        notes = f"No outliers (n={len(series)}, α=10%)"  # noqa: RUF001
    else:
        outlier_str = ", ".join(f"{yr}: {series[yr]:.1f}" for yr in sorted(outlier_labels))
        notes = f"Outliers detected (n={len(series)}, α=10%): {outlier_str} m³/s"  # noqa: RUF001

    insert_result(
        db,
        SERIES_TYPE,
        station_code,
        GRUBBS_BECK_TEST_ID,
        int(series.index[0]),
        int(series.index[-1]),
        notes,
        passed,
    )
    status = "PASSED" if passed else "FAILED"
    print(f"  Grubbs-Beck  [{status}]  {notes}")


def run_kruskal_wallis(db: Database, station_code: str, label: str) -> None:
    series = fetch_wq(db, station_code)
    if series.empty:
        print(f"  WARNING: no WQ data for {label}, skipping Kruskal-Wallis.")
        return

    test = KruskalWallisTest(k=2, alpha=0.05)
    passed, _ = test.run(series)
    p_value = test.last_p_value(series)

    split_year = series.index[len(series) // 2]
    notes = f"k=2 groups split at {split_year} (n={len(series)}, α=5%, p={p_value:.4f})"  # noqa: RUF001

    insert_result(
        db,
        SERIES_TYPE,
        station_code,
        KRUSKAL_WALLIS_TEST_ID,
        int(series.index[0]),
        int(series.index[-1]),
        notes,
        passed,
    )
    status = "PASSED" if passed else "FAILED"
    print(f"  Kruskal-Wallis [{status}]  {notes}")


def run_wald_wolfowitz(db: Database, station_code: str, label: str) -> None:
    series = fetch_wq(db, station_code)
    if series.empty:
        print(f"  WARNING: no WQ data for {label}, skipping Wald-Wolfowitz.")
        return

    test = WaldWolfowitzRunsTest(alpha=0.05)
    passed, _ = test.run(series)
    notes = f"n={len(series)}, α=5%, p={test.p_value:.4f}"  # noqa: RUF001

    insert_result(
        db,
        SERIES_TYPE,
        station_code,
        WALD_WOLFOWITZ_TEST_ID,
        int(series.index[0]),
        int(series.index[-1]),
        notes,
        passed,
    )
    status = "PASSED" if passed else "FAILED"
    print(f"  Wald-Wolfowitz [{status}]  {notes}")


def run_mann_kendall(db: Database, station_code: str, label: str) -> None:
    series = fetch_wq(db, station_code)
    if series.empty:
        print(f"  WARNING: no WQ data for {label}, skipping Mann-Kendall.")
        return

    test = MannKendallTest(alpha=0.05)
    passed, _ = test.run(series)
    notes = f"n={len(series)}, α=5%, p={test.p_value:.4f}"  # noqa: RUF001

    insert_result(
        db,
        SERIES_TYPE,
        station_code,
        MANN_KENDALL_TEST_ID,
        int(series.index[0]),
        int(series.index[-1]),
        notes,
        passed,
    )
    status = "PASSED" if passed else "FAILED"
    print(f"  Mann-Kendall   [{status}]  {notes}")


def run_spearman_rank(db: Database, station_code: str, label: str) -> None:
    series = fetch_wq(db, station_code)
    if series.empty:
        print(f"  WARNING: no WQ data for {label}, skipping Spearman.")
        return

    test = SpearmanRankTest(alpha=0.05)
    passed, _ = test.run(series)
    notes = f"ρ={test.correlation:.4f}, n={len(series)}, α=5%, p={test.p_value:.4f}"  # noqa: RUF001

    insert_result(
        db,
        SERIES_TYPE,
        station_code,
        SPEARMAN_RANK_TEST_ID,
        int(series.index[0]),
        int(series.index[-1]),
        notes,
        passed,
    )
    status = "PASSED" if passed else "FAILED"
    print(f"  Spearman       [{status}]  {notes}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run statistical tests on annual WQ series.")
    parser.add_argument(
        "--all",
        action="store_true",
        help=f"Run for all stations with WQ series > {MIN_YEARS} years (default: 3 example stations).",  # noqa: E501
    )
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(
            f"ERROR: {DB_PATH} not found. Run raw_data_parser.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    db = Database(str(DB_PATH))
    db.create_stat_tests_schema()

    if args.all:
        stations = fetch_all_stations(db)
        print(f"Found {len(stations)} stations with WQ series > {MIN_YEARS} years.\n")
    else:
        stations = STATIONS

    for i, (station_code, station_name, river_name) in enumerate(stations, 1):
        prefix = f"[{i}/{len(stations)}] " if args.all else ""
        print(f"\n{prefix}{station_name} ({river_name})")
        run_grubbs_beck(db, station_code, station_name)
        run_kruskal_wallis(db, station_code, station_name)
        run_wald_wolfowitz(db, station_code, station_name)
        run_mann_kendall(db, station_code, station_name)
        run_spearman_rank(db, station_code, station_name)

    db.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
