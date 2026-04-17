#!/usr/bin/env python3
"""
Compute IMGW-notation hydrology statistics from the measurements table
and store them in derived stats tables within the same DuckDB database.

Usage:
    uv run python stats_calculator.py

Requires hydro.duckdb to exist and contain measurements data.
Run raw_data_parser.py first if it does not.

IMGW notation:
    Q  = flow [m³/s]          W  = water level [cm]
    N  = minimum              S  = mean (average)
    Z  = median               W prefix = maximum

Tables produced:
    stats_monthly   — NQ SQ ZQ WQ  NW SW ZW WW  per station / calendar year+month
    stats_annual    — same per station / hydrological year
    stats_alltime   — NNQ WWQ SWQ SNQ SSQ  per station (derived from monthly)
"""

import sys
from pathlib import Path

from modules.db import DuckDatabase as Database
from modules.db.stats_repository import StatsRepository

DB_PATH = Path(__file__).parent / "hydro.duckdb"


def main() -> None:
    if not DB_PATH.exists():
        print(
            f"ERROR: {DB_PATH} not found. Run raw_data_parser.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    db = Database(str(DB_PATH))

    row_count = db.con.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
    if row_count == 0:
        print("ERROR: measurements table is empty. Load data first.", file=sys.stderr)
        db.close()
        sys.exit(1)

    print(f"Source: {row_count:,} measurement rows in {DB_PATH.name}")

    db.create_stats_schema()
    stats = StatsRepository(db.con)

    print("Computing monthly statistics ...", end=" ", flush=True)
    n = stats.compute_monthly()
    print(f"{n:,} rows")

    print("Computing annual statistics  ...", end=" ", flush=True)
    n = stats.compute_annual()
    print(f"{n:,} rows")

    print("Computing all-time statistics...", end=" ", flush=True)
    n = stats.compute_alltime()
    print(f"{n:,} stations")

    print("\nDone.")


if __name__ == "__main__":
    main()
