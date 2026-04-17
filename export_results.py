"""
export_results.py — Export processed results from local DuckDB to PostgreSQL.

Reads connection settings from a .env file (or environment variables):

    POSTGRES_HOST     (default: localhost)
    POSTGRES_PORT     (default: 5432)
    POSTGRES_DB
    POSTGRES_USER
    POSTGRES_PASSWORD
    POSTGRES_SCHEMA   (default: hydro)
    DUCKDB_PATH       (default: hydro.duckdb)

Exported tables (in the configured schema):
    stations          ← gauges_list
    stats_alltime     ← stats_alltime  (NNQ, WWQ, SWQ, SNQ, SSQ)
    estimations       ← fitted_distributions (latest fit per station)
    estimated_flows   ← estimated_discharges (FK → estimations)
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from modules.db import DuckDatabase, PostgresDatabase

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

load_dotenv()


def _env(key: str, default: str | None = None) -> str:
    val = os.getenv(key, default)
    if val is None:
        print(f"ERROR: required environment variable {key!r} is not set.", file=sys.stderr)
        sys.exit(1)
    return val


DUCKDB_PATH = Path(_env("DUCKDB_PATH", "hydro.duckdb"))
PG_HOST = _env("POSTGRES_HOST", "localhost")
PG_PORT = int(_env("POSTGRES_PORT", "5432"))
PG_DB = _env("POSTGRES_DB")
PG_USER = _env("POSTGRES_USER")
PG_PASSWORD = _env("POSTGRES_PASSWORD")
PG_SCHEMA = _env("POSTGRES_SCHEMA", "hydro")


# ---------------------------------------------------------------------------
# Fetch helpers (DuckDB → Python)
# ---------------------------------------------------------------------------


def fetch_stations(duck: DuckDatabase) -> list[tuple]:
    """Return all rows from gauges_list."""
    return duck.con.execute("""
        SELECT station_code, station_name, river_name, lat, lon, uuid::VARCHAR
        FROM gauges_list
        ORDER BY station_code
    """).fetchall()


def fetch_stats_alltime(duck: DuckDatabase) -> list[tuple]:
    """Return all-time aggregate rows that have a matching station."""
    return duck.con.execute("""
        SELECT a.station_code, a.NNQ, a.WWQ, a.SWQ, a.SNQ, a.SSQ, a.mes_count
        FROM stats_alltime a
        INNER JOIN gauges_list g USING (station_code)
        ORDER BY a.station_code
    """).fetchall()


def fetch_fitted_estimations(duck: DuckDatabase) -> list[tuple]:
    """
    Return the latest fitted distribution parameters per
    (station_code, distribution, method, frequency).

    Uses MAX(id) subquery instead of ROW_NUMBER to avoid the DuckDB binder
    bug with column references inside CTEs.

    Row shape:
        (station_code, distribution, method, frequency,
         mu_log, sigma_log, n, year_start, year_end)
    """
    return duck.con.execute("""
        SELECT
            fd.station_code,
            d.name                                               AS distribution,
            em.name                                              AS method,
            f.name                                               AS frequency,
            (fd.distribution_params->>'mu_log')::DOUBLE          AS mu_log,
            (fd.distribution_params->>'sigma_log')::DOUBLE       AS sigma_log,
            (fd.source_timeseries_info->>'n')::INTEGER           AS n,
            (fd.source_timeseries_info->>'year_start')::INTEGER  AS year_start,
            (fd.source_timeseries_info->>'year_end')::INTEGER    AS year_end
        FROM fitted_distributions fd
        JOIN distributions      d  ON d.id  = fd.distribution_id
        JOIN estimation_methods em ON em.id = fd.estimation_method_id
        JOIN frequencies        f  ON f.id  = fd.frequency_id
        WHERE fd.id IN (
            SELECT MAX(id)
            FROM fitted_distributions
            GROUP BY station_code, distribution_id, estimation_method_id, frequency_id
        )
        ORDER BY fd.station_code, d.name, em.name, f.name
    """).fetchall()


def fetch_estimated_flows(duck: DuckDatabase) -> list[tuple]:
    """
    Return the latest Q estimate per
    (station_code, distribution, method, frequency, return_period).

    Uses MAX(id) subquery instead of ROW_NUMBER to avoid the DuckDB binder
    bug with column references inside CTEs.

    Row shape:
        (station_code, distribution, method, frequency,
         return_period, probability, q_estimated_m3s)
    """
    return duck.con.execute("""
        SELECT
            ed.station_code,
            d.name                                  AS distribution,
            em.name                                 AS method,
            f.name                                  AS frequency,
            ed.return_period,
            1.0 / ed.return_period                  AS probability,
            (ed.notes->>'Q_estimated_m3s')::DOUBLE  AS q_estimated_m3s
        FROM estimated_discharges ed
        JOIN distributions      d  ON d.id  = ed.distribution_id
        JOIN estimation_methods em ON em.id = ed.estimation_method_id
        JOIN frequencies        f  ON f.id  = ed.frequency_id
        WHERE ed.id IN (
            SELECT MAX(id)
            FROM estimated_discharges
            GROUP BY station_code,
                     distribution_id,
                     estimation_method_id,
                     frequency_id,
                     return_period
        )
        ORDER BY ed.station_code, d.name, em.name, f.name, ed.return_period
    """).fetchall()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    if not DUCKDB_PATH.exists():
        print(f"ERROR: {DUCKDB_PATH} not found. Run raw_data_parser.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Source:      {DUCKDB_PATH}")
    print(f"Target:      {PG_USER}@{PG_HOST}:{PG_PORT}/{PG_DB}  (schema: {PG_SCHEMA})")

    duck = DuckDatabase(str(DUCKDB_PATH))
    pg = PostgresDatabase(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASSWORD,
        pg_schema=PG_SCHEMA,
    )

    try:
        print("\n[1/5] Setting up PostgreSQL schema …")
        pg.setup_schema()
        print("      Done.")

        print("[2/5] Exporting stations …")
        n = pg.upsert_stations(fetch_stations(duck))
        print(f"      {n} stations upserted.")

        print("[3/5] Exporting all-time aggregates …")
        n = pg.upsert_stats_alltime(fetch_stats_alltime(duck))
        print(f"      {n} rows upserted.")

        print("[4/5] Fetching estimation data from DuckDB …")
        est_rows = fetch_fitted_estimations(duck)
        flow_rows = fetch_estimated_flows(duck)
        station_codes = list({r[0] for r in est_rows})
        print(
            f"      {len(est_rows)} fitted distributions, "
            f"{len(flow_rows)} flow estimates "
            f"across {len(station_codes)} stations."
        )

        print("[5/5] Exporting estimations + flows …")
        if est_rows:
            n_est, n_flows = pg.replace_estimations_and_flows(station_codes, est_rows, flow_rows)
            print(f"      {n_est} estimations, {n_flows} estimated flows inserted.")
        else:
            print("      No estimation data found — run run_estimation.py first.")

        print("\nExport complete.")

    finally:
        duck.close()
        pg.close()


if __name__ == "__main__":
    main()
