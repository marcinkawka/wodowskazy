#!/usr/bin/env python3
"""
Entry point: parse IMGW-PIB river gauge CSV files into a DuckDB database.

Usage:
    uv run python raw_data_parser.py [--all]

By default processes only the first 10 files of each type.
Pass --all to process all available files.
"""

import sys
from pathlib import Path

from modules.db import Database
from modules.db.repository import (
    GaugeRepository,
    MeasurementRepository,
    PhenomenonRepository,
)
from modules.db.service import HydroService

EXTRACTED_DIR = Path(__file__).parent / "extracted_data"
DB_PATH = Path(__file__).parent / "hydro.duckdb"
DEFAULT_FILE_LIMIT = 10


def run(file_limit: int | None = DEFAULT_FILE_LIMIT) -> None:
    if not EXTRACTED_DIR.exists():
        print(
            f"ERROR: {EXTRACTED_DIR} does not exist. "
            "Run scripts/extract_data.sh first.",
            file=sys.stderr,
        )
        sys.exit(1)

    db = Database(str(DB_PATH))
    db.create_schema()

    service = HydroService(
        gauge_repo=GaugeRepository(db.con),
        measurement_repo=MeasurementRepository(db.con),
        phenomenon_repo=PhenomenonRepository(db.con),
    )

    codz_files = sorted(EXTRACTED_DIR.rglob("codz_*.csv"))
    zjaw_files = sorted(EXTRACTED_DIR.rglob("zjaw_*.csv"))

    if file_limit is not None:
        codz_files = codz_files[:file_limit]
        zjaw_files = zjaw_files[:file_limit]

    print(f"Processing {len(codz_files)} CODZ + {len(zjaw_files)} ZJAW files.")

    total_meas, total_phen, errors = 0, 0, []

    for i, path in enumerate(codz_files, 1):
        result = service.process_codz(path)
        total_meas += result.rows
        status = "OK" if result.ok else f"ERR: {result.error}"
        print(f"  [{i:3}/{len(codz_files)}] {path.name}: {result.rows} rows  {status}")
        if not result.ok:
            errors.append(result)

    for i, path in enumerate(zjaw_files, 1):
        result = service.process_zjaw(path)
        total_phen += result.rows
        status = "OK" if result.ok else f"ERR: {result.error}"
        print(f"  [{i:3}/{len(zjaw_files)}] {path.name}: {result.rows} rows  {status}")
        if not result.ok:
            errors.append(result)

    gauge_count = db.con.execute("SELECT COUNT(*) FROM gauges_list").fetchone()[0]
    print(f"\nDone. Gauges: {gauge_count:,} | Measurements: {total_meas:,} | Phenomena: {total_phen:,}")
    if errors:
        print(f"Errors: {len(errors)}")
    print(f"Database: {DB_PATH}")
    db.close()


if __name__ == "__main__":
    process_all = "--all" in sys.argv
    run(file_limit=None if process_all else DEFAULT_FILE_LIMIT)
