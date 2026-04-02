#!/usr/bin/env python3
"""
Run Grubbs-Beck outlier test and Kruskal-Wallis stationarity test on annual
maximum flows (WQ) for selected stations and persist results to the database.

Stations tested
---------------
  DĘBLIN   — Wisła,        station_code 151210120
  KŁODZKO  — Nysa Kłodzka, station_code 150160180

Usage
-----
    uv run run_stat_tests.py
"""

import sys
from pathlib import Path

from modules.db import Database
from modules.stat_tests import (
    GrubbsBeckTest,
    KruskalWallisTest,
    MannKendallTest,
    SpearmanRankTest,
    WaldWolfowitzRunsTest,
)

DB_PATH = Path(__file__).parent / "hydro.duckdb"

STATIONS = [
    ("151210120", "DĘBLIN", "Wisła"),
    ("150160180", "KŁODZKO", "Nysa Kłodzka"),
]

GRUBBS_BECK_TEST_ID = 1
KRUSKAL_WALLIS_TEST_ID = 2
WALD_WOLFOWITZ_TEST_ID = 4
MANN_KENDALL_TEST_ID = 5
SPEARMAN_RANK_TEST_ID = 6
SERIES_TYPE = "WQ_annual"


def fetch_wq(db: Database, station_code: str) -> tuple[list[int], list[float]]:
    rows = db.con.execute(
        "SELECT hydro_year, WQ FROM stats_annual"
        " WHERE station_code = ? AND WQ IS NOT NULL"
        " ORDER BY hydro_year",
        [station_code],
    ).fetchall()
    years = [r[0] for r in rows]
    values = [r[1] for r in rows]
    return years, values


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
    next_id = db.con.execute(
        "SELECT nextval('stat_test_results_id_seq')"
    ).fetchone()[0]
    db.con.execute(
        "INSERT INTO stat_test_results"
        " (id, series_type, station_code, test_id,"
        "  period_start, period_end, result_notes, result)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [next_id, series_type, station_code, test_id,
         period_start, period_end, notes, result],
    )


def run_grubbs_beck(db: Database, station_code: str, label: str) -> None:
    years, values = fetch_wq(db, station_code)
    if not values:
        print(f"  WARNING: no WQ data for {label}, skipping Grubbs-Beck.")
        return

    test = GrubbsBeckTest(alpha=0.10)
    passed, outliers = test.run(values)

    if passed:
        notes = f"No outliers (n={len(values)}, α=10%)"
    else:
        outlier_str = ", ".join(f"{v:.1f}" for v in sorted(outliers))
        notes = f"Outliers detected (n={len(values)}, α=10%): {outlier_str} m³/s"

    insert_result(
        db, SERIES_TYPE, station_code, GRUBBS_BECK_TEST_ID,
        years[0], years[-1], notes, passed,
    )
    status = "PASSED" if passed else "FAILED"
    print(f"  Grubbs-Beck  [{status}]  {notes}")


def run_kruskal_wallis(db: Database, station_code: str, label: str) -> None:
    years, values = fetch_wq(db, station_code)
    if not values:
        print(f"  WARNING: no WQ data for {label}, skipping Kruskal-Wallis.")
        return

    test = KruskalWallisTest(k=2, alpha=0.05)
    passed, _ = test.run(values)
    p_value = test.last_p_value(values)

    mid = len(values) // 2
    split_year = years[mid]
    notes = (
        f"k=2 groups split at {split_year}"
        f" (n={len(values)}, α=5%, p={p_value:.4f})"
    )

    insert_result(
        db, SERIES_TYPE, station_code, KRUSKAL_WALLIS_TEST_ID,
        years[0], years[-1], notes, passed,
    )
    status = "PASSED" if passed else "FAILED"
    print(f"  Kruskal-Wallis [{status}]  {notes}")


def run_wald_wolfowitz(db: Database, station_code: str, label: str) -> None:
    years, values = fetch_wq(db, station_code)
    if not values:
        print(f"  WARNING: no WQ data for {label}, skipping Wald-Wolfowitz.")
        return

    test = WaldWolfowitzRunsTest(alpha=0.05)
    passed, _ = test.run(values)
    notes = f"n={len(values)}, α=5%, p={test.p_value:.4f}"

    insert_result(
        db, SERIES_TYPE, station_code, WALD_WOLFOWITZ_TEST_ID,
        years[0], years[-1], notes, passed,
    )
    status = "PASSED" if passed else "FAILED"
    print(f"  Wald-Wolfowitz [{status}]  {notes}")


def run_mann_kendall(db: Database, station_code: str, label: str) -> None:
    years, values = fetch_wq(db, station_code)
    if not values:
        print(f"  WARNING: no WQ data for {label}, skipping Mann-Kendall.")
        return

    test = MannKendallTest(alpha=0.05)
    passed, _ = test.run(values)
    notes = f"n={len(values)}, α=5%, p={test.p_value:.4f}"

    insert_result(
        db, SERIES_TYPE, station_code, MANN_KENDALL_TEST_ID,
        years[0], years[-1], notes, passed,
    )
    status = "PASSED" if passed else "FAILED"
    print(f"  Mann-Kendall   [{status}]  {notes}")


def run_spearman_rank(db: Database, station_code: str, label: str) -> None:
    years, values = fetch_wq(db, station_code)
    if not values:
        print(f"  WARNING: no WQ data for {label}, skipping Spearman.")
        return

    test = SpearmanRankTest(alpha=0.05)
    passed, _ = test.run(values)
    notes = (
        f"ρ={test.correlation:.4f}, n={len(values)}, α=5%, p={test.p_value:.4f}"
    )

    insert_result(
        db, SERIES_TYPE, station_code, SPEARMAN_RANK_TEST_ID,
        years[0], years[-1], notes, passed,
    )
    status = "PASSED" if passed else "FAILED"
    print(f"  Spearman       [{status}]  {notes}")


def main() -> None:
    if not DB_PATH.exists():
        print(
            f"ERROR: {DB_PATH} not found. Run raw_data_parser.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    db = Database(str(DB_PATH))
    db.create_stat_tests_schema()

    for station_code, station_name, river_name in STATIONS:
        print(f"\n{station_name} ({river_name})")
        run_grubbs_beck(db, station_code, station_name)
        run_kruskal_wallis(db, station_code, station_name)
        run_wald_wolfowitz(db, station_code, station_name)
        run_mann_kendall(db, station_code, station_name)
        run_spearman_rank(db, station_code, station_name)

    db.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
