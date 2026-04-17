"""
Database backends for the wodowskazy pipeline.

AbstractDatabase (ABC)
  ├── DuckDatabase   — local DuckDB, operational store for all pipeline stages
  └── PostgresDatabase — PostgreSQL export target (stations, aggregates, estimations)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import duckdb
import psycopg2
import psycopg2.extras

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class Database(ABC):
    """Common interface for all database backends."""

    @abstractmethod
    def setup_schema(self) -> None:
        """Create (or migrate) all tables owned by this backend."""

    @abstractmethod
    def close(self) -> None:
        """Release the underlying connection."""


# ---------------------------------------------------------------------------
# DuckDB — operational store
# ---------------------------------------------------------------------------


class DuckDatabase(Database):
    """
    Manages the DuckDB connection and schema lifecycle.
    Uses CREATE TABLE IF NOT EXISTS — safe to call on an existing database;
    existing data is preserved and only missing tables are created.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self.con: duckdb.DuckDBPyConnection = duckdb.connect(path)

    # ------------------------------------------------------------------
    # AbstractDatabase interface
    # ------------------------------------------------------------------

    def setup_schema(self) -> None:
        """Create all DuckDB schemas (raw data + stats + tests + frequency analysis)."""
        self.create_schema()
        self.create_stats_schema()
        self.create_stat_tests_schema()
        self.create_frequency_analysis_schema()

    def close(self) -> None:
        self.con.close()

    # ------------------------------------------------------------------
    # Granular schema helpers (kept for backward compat / selective use)
    # ------------------------------------------------------------------

    def create_schema(self) -> None:
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS gauges_list (
                station_code  VARCHAR PRIMARY KEY,
                station_name  VARCHAR,
                river_name    VARCHAR,
                lat           DOUBLE,
                lon           DOUBLE,
                uuid          UUID DEFAULT gen_random_uuid()
            )
        """)
        # Migration: add uuid to existing databases that predate this column.
        self.con.execute("""
            ALTER TABLE gauges_list ADD COLUMN IF NOT EXISTS uuid UUID
        """)
        self.con.execute("""
            UPDATE gauges_list SET uuid = gen_random_uuid() WHERE uuid IS NULL
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS measurements (
                station_code   VARCHAR     NOT NULL,
                measured_at    TIMESTAMPTZ NOT NULL,
                hydro_year     INTEGER,
                hydro_month    INTEGER,
                calendar_month INTEGER,
                water_level_cm INTEGER,
                flow_m3s       DOUBLE,
                water_temp_c   DOUBLE,
                PRIMARY KEY (station_code, measured_at)
            )
        """)
        self.con.execute("""
            CREATE INDEX IF NOT EXISTS idx_measurements_station
            ON measurements (station_code)
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS phenomena (
                station_code        VARCHAR     NOT NULL,
                measured_at         TIMESTAMPTZ NOT NULL,
                hydro_year          INTEGER,
                hydro_month         INTEGER,
                ice_thickness_cm    INTEGER,
                ice_phenomenon_code VARCHAR,
                ice_phenomenon_pct  INTEGER,
                overgrowth_code     VARCHAR,
                PRIMARY KEY (station_code, measured_at)
            )
        """)
        self.con.execute("""
            CREATE INDEX IF NOT EXISTS idx_phenomena_station
            ON phenomena (station_code)
        """)

    def create_stats_schema(self) -> None:
        """
        Create (or recreate) derived statistics tables.
        Stats tables are fully recomputed each run so CREATE OR REPLACE is safe.

        IMGW notation:  N=min  S=avg  Z=median  W=max
                        Q=flow [m³/s]   W=water level [cm]
        Monthly/annual: NQ SQ ZQ WQ  NW SW ZW WW  + mes_count
        All-time:       NNQ WWQ SWQ SNQ SSQ        + mes_count
        """
        self.con.execute("""
            CREATE OR REPLACE TABLE stats_monthly (
                station_code  VARCHAR  NOT NULL,
                year          INTEGER  NOT NULL,
                month         INTEGER  NOT NULL,
                NQ            DOUBLE,
                SQ            DOUBLE,
                ZQ            DOUBLE,
                WQ            DOUBLE,
                NW            DOUBLE,
                SW            DOUBLE,
                ZW            DOUBLE,
                WW            DOUBLE,
                mes_count     INTEGER  NOT NULL,
                PRIMARY KEY (station_code, year, month)
            )
        """)
        self.con.execute("""
            CREATE INDEX IF NOT EXISTS idx_stats_monthly_station
            ON stats_monthly (station_code)
        """)
        self.con.execute("""
            CREATE OR REPLACE TABLE stats_annual (
                station_code  VARCHAR  NOT NULL,
                hydro_year    INTEGER  NOT NULL,
                NQ            DOUBLE,
                SQ            DOUBLE,
                ZQ            DOUBLE,
                WQ            DOUBLE,
                NW            DOUBLE,
                SW            DOUBLE,
                ZW            DOUBLE,
                WW            DOUBLE,
                mes_count     INTEGER  NOT NULL,
                PRIMARY KEY (station_code, hydro_year)
            )
        """)
        self.con.execute("""
            CREATE INDEX IF NOT EXISTS idx_stats_annual_station
            ON stats_annual (station_code)
        """)
        self.con.execute("""
            CREATE OR REPLACE TABLE stats_alltime (
                station_code  VARCHAR PRIMARY KEY,
                NNQ           DOUBLE,
                WWQ           DOUBLE,
                SWQ           DOUBLE,
                SNQ           DOUBLE,
                SSQ           DOUBLE,
                mes_count     INTEGER  NOT NULL
            )
        """)

    def create_stat_tests_schema(self) -> None:
        """
        Create tables for statistical tests catalogue and test results.
        stat_tests is seeded with the three standard tests on first creation.
        stat_test_results is append-only; re-running the script adds new rows.
        """
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS stat_tests (
                id    INTEGER PRIMARY KEY,
                name  VARCHAR NOT NULL UNIQUE
            )
        """)
        self.con.execute("""
            INSERT INTO stat_tests (id, name)
            VALUES
                (1, 'Grubbs-Beck test'),
                (2, 'Kruskal-Wallis test'),
                (3, 'Chi-square test'),
                (4, 'Wald-Wolfowitz runs test'),
                (5, 'Mann-Kendall test'),
                (6, 'Spearman rank correlation test')
            ON CONFLICT (id) DO NOTHING
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS stat_test_results (
                id            INTEGER PRIMARY KEY,
                series_type   VARCHAR  NOT NULL,
                station_code  VARCHAR  NOT NULL,
                test_id       INTEGER  NOT NULL REFERENCES stat_tests(id),
                period_start  INTEGER,
                period_end    INTEGER,
                result_notes  VARCHAR,
                result        BOOLEAN  NOT NULL
            )
        """)
        self.con.execute("""
            CREATE SEQUENCE IF NOT EXISTS stat_test_results_id_seq START 1
        """)

    def create_frequency_analysis_schema(self) -> None:
        """
        Create catalogue and result tables for flood-frequency analysis.

        Catalogues (seeded, append-only):
            distributions        — statistical distribution families
            estimation_methods   — parameter estimation approaches
            frequencies          — source series type (annual / seasonal)

        Results:
            estimated_discharges — Q_100 / Q_1000 estimates per station,
                                   linked to distribution, method and frequency;
                                   append-only, notes stored as JSON.
        """
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS distributions (
                id              INTEGER PRIMARY KEY,
                name            VARCHAR NOT NULL UNIQUE,
                additional_note TEXT
            )
        """)
        self.con.execute("""
            INSERT INTO distributions (id, name, additional_note)
            VALUES
                (1, 'Gumbel',          NULL),
                (2, 'Log-Normal',      NULL),
                (3, 'Pearson III',     NULL),
                (4, 'Log-Pearson III', NULL),
                (5, 'GEV',             NULL)
            ON CONFLICT (id) DO NOTHING
        """)

        self.con.execute("""
            CREATE TABLE IF NOT EXISTS estimation_methods (
                id   INTEGER PRIMARY KEY,
                name VARCHAR NOT NULL UNIQUE
            )
        """)
        self.con.execute("""
            INSERT INTO estimation_methods (id, name)
            VALUES
                (1, 'Method of Moments'),
                (2, 'Maximum Likelihood'),
                (3, 'Linear Moments'),
                (4, 'Weighted Moments')
            ON CONFLICT (id) DO NOTHING
        """)

        self.con.execute("""
            CREATE TABLE IF NOT EXISTS frequencies (
                id   INTEGER PRIMARY KEY,
                name VARCHAR NOT NULL UNIQUE
            )
        """)
        self.con.execute("""
            INSERT INTO frequencies (id, name)
            VALUES
                (1, 'annual'),
                (2, 'winter'),
                (3, 'summer')
            ON CONFLICT (id) DO NOTHING
        """)

        self.con.execute("""
            CREATE TABLE IF NOT EXISTS fitted_distributions (
                id                    INTEGER PRIMARY KEY,
                estimation_method_id  INTEGER  NOT NULL REFERENCES estimation_methods(id),
                distribution_id       INTEGER  NOT NULL REFERENCES distributions(id),
                frequency_id          INTEGER  NOT NULL REFERENCES frequencies(id),
                distribution_params   JSON     NOT NULL,
                station_code          VARCHAR  NOT NULL REFERENCES gauges_list(station_code),
                source_timeseries_info JSON    NOT NULL
            )
        """)
        self.con.execute("""
            CREATE SEQUENCE IF NOT EXISTS fitted_distributions_id_seq START 1
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS estimated_discharges (
                id                   INTEGER PRIMARY KEY,
                station_code         VARCHAR  NOT NULL REFERENCES gauges_list(station_code),
                return_period        INTEGER  NOT NULL CHECK (return_period IN (100, 1000)),
                distribution_id      INTEGER  NOT NULL REFERENCES distributions(id),
                estimation_method_id INTEGER  NOT NULL REFERENCES estimation_methods(id),
                frequency_id         INTEGER  NOT NULL REFERENCES frequencies(id),
                notes                JSON
            )
        """)
        self.con.execute("""
            CREATE SEQUENCE IF NOT EXISTS estimated_discharges_id_seq START 1
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS ci_estimates (
                id                    INTEGER PRIMARY KEY,
                fitted_distribution_id INTEGER NOT NULL REFERENCES fitted_distributions(id),
                alpha                 DOUBLE  NOT NULL,
                n_bootstrap           INTEGER NOT NULL,
                ci_data               JSON    NOT NULL
            )
        """)
        self.con.execute("""
            CREATE SEQUENCE IF NOT EXISTS ci_estimates_id_seq START 1
        """)


# ---------------------------------------------------------------------------
# PostgreSQL — export target
# ---------------------------------------------------------------------------


class PostgresDatabase(Database):
    """
    PostgreSQL export target for processed results.

    Schema (all tables in the configured pg_schema):
        stations          — station metadata from gauges_list
        stats_alltime     — all-time aggregate flows (NNQ, WWQ, SWQ, SNQ, SSQ)
        stats_estimations — Q₁₀₀ / Q₁₀₀₀ estimates with distribution details
    """

    def __init__(
        self,
        host: str,
        port: int,
        dbname: str,
        user: str,
        password: str,
        pg_schema: str = "hydro",
    ) -> None:
        self._schema = pg_schema
        self.con = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
        )
        self.con.autocommit = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _execute(self, sql: str, params: Any = None) -> None:
        with self.con.cursor() as cur:
            cur.execute(sql, params)

    def _executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        with self.con.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, rows, page_size=500)

    def _s(self, table: str) -> str:
        """Return schema-qualified table name."""
        return f"{self._schema}.{table}"

    # ------------------------------------------------------------------
    # AbstractDatabase interface
    # ------------------------------------------------------------------

    def setup_schema(self) -> None:
        """Create the export schema and all tables (idempotent)."""
        self._execute(f"CREATE SCHEMA IF NOT EXISTS {self._schema}")
        self._execute(f"""
            CREATE TABLE IF NOT EXISTS {self._s("stations")} (
                station_code  VARCHAR(20)      PRIMARY KEY,
                station_name  VARCHAR(200),
                river_name    VARCHAR(200),
                lat           DOUBLE PRECISION,
                lon           DOUBLE PRECISION,
                uuid          UUID
            )
        """)
        self._execute(f"""
            CREATE TABLE IF NOT EXISTS {self._s("stats_alltime")} (
                station_code  VARCHAR(20)      PRIMARY KEY
                    REFERENCES {self._s("stations")}(station_code),
                "NNQ"         DOUBLE PRECISION,
                "WWQ"         DOUBLE PRECISION,
                "SWQ"         DOUBLE PRECISION,
                "SNQ"         DOUBLE PRECISION,
                "SSQ"         DOUBLE PRECISION,
                mes_count     INTEGER          NOT NULL
            )
        """)
        # Migrate: drop the old flat estimations table if it still exists.
        self._execute(f"DROP TABLE IF EXISTS {self._s('stats_estimations')}")
        self._execute(f"""
            CREATE TABLE IF NOT EXISTS {self._s("estimations")} (
                id            SERIAL           PRIMARY KEY,
                station_code  VARCHAR(20)      NOT NULL
                    REFERENCES {self._s("stations")}(station_code),
                distribution  VARCHAR(50)      NOT NULL,
                method        VARCHAR(50)      NOT NULL,
                frequency     VARCHAR(20)      NOT NULL,
                mu_log        DOUBLE PRECISION,
                sigma_log     DOUBLE PRECISION,
                n             INTEGER,
                year_start    INTEGER,
                year_end      INTEGER,
                exported_at   TIMESTAMPTZ      DEFAULT NOW(),
                UNIQUE (station_code, distribution, method, frequency)
            )
        """)
        self._execute(f"""
            CREATE TABLE IF NOT EXISTS {self._s("estimated_flows")} (
                id              SERIAL           PRIMARY KEY,
                estimation_id   INTEGER          NOT NULL
                    REFERENCES {self._s("estimations")}(id) ON DELETE CASCADE,
                return_period   INTEGER          NOT NULL,
                probability     DOUBLE PRECISION NOT NULL,
                q_estimated_m3s DOUBLE PRECISION
            )
        """)
        self.con.commit()

    def close(self) -> None:
        self.con.close()

    # ------------------------------------------------------------------
    # Upsert helpers used by export_results.py
    # ------------------------------------------------------------------

    def upsert_stations(self, rows: list[tuple[Any, ...]]) -> int:
        """
        Insert or update station rows.

        Each row: (station_code, station_name, river_name, lat, lon, uuid)
        Returns number of rows processed.
        """
        sql = f"""
            INSERT INTO {self._s("stations")}
                (station_code, station_name, river_name, lat, lon, uuid)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (station_code) DO UPDATE SET
                station_name = EXCLUDED.station_name,
                river_name   = EXCLUDED.river_name,
                lat          = EXCLUDED.lat,
                lon          = EXCLUDED.lon,
                uuid         = EXCLUDED.uuid
        """
        self._executemany(sql, rows)
        self.con.commit()
        return len(rows)

    def upsert_stats_alltime(self, rows: list[tuple[Any, ...]]) -> int:
        """
        Insert or update all-time aggregate rows.

        Each row: (station_code, NNQ, WWQ, SWQ, SNQ, SSQ, mes_count)
        Returns number of rows processed.
        """
        sql = f"""
            INSERT INTO {self._s("stats_alltime")}
                (station_code, "NNQ", "WWQ", "SWQ", "SNQ", "SSQ", mes_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (station_code) DO UPDATE SET
                "NNQ"      = EXCLUDED."NNQ",
                "WWQ"      = EXCLUDED."WWQ",
                "SWQ"      = EXCLUDED."SWQ",
                "SNQ"      = EXCLUDED."SNQ",
                "SSQ"      = EXCLUDED."SSQ",
                mes_count  = EXCLUDED.mes_count
        """
        self._executemany(sql, rows)
        self.con.commit()
        return len(rows)

    def replace_estimations_and_flows(
        self,
        station_codes: list[str],
        est_rows: list[tuple[Any, ...]],
        flow_rows: list[tuple[Any, ...]],
    ) -> tuple[int, int]:
        """
        Delete existing estimations (flows cascade) for the given stations,
        then insert fresh estimations and their estimated flows.

        est_rows  — one row per fitted distribution:
            (station_code, distribution, method, frequency,
             mu_log, sigma_log, n, year_start, year_end)

        flow_rows — one row per return-period estimate:
            (station_code, distribution, method, frequency,
             return_period, probability, q_estimated_m3s)

        Returns (n_estimations, n_flows).
        """
        if station_codes:
            with self.con.cursor() as cur:
                cur.execute(
                    f"DELETE FROM {self._s('estimations')} WHERE station_code = ANY(%s)",
                    (station_codes,),
                )

        if not est_rows:
            self.con.commit()
            return 0, 0

        # Bulk-insert estimations; fetch=True collects RETURNING rows across
        # all internal pages (execute_values paginates at page_size=100 by
        # default, so cur.fetchall() alone would only capture the last page).
        with self.con.cursor() as cur:
            returned = psycopg2.extras.execute_values(
                cur,
                f"""
                INSERT INTO {self._s("estimations")}
                    (station_code, distribution, method, frequency,
                     mu_log, sigma_log, n, year_start, year_end)
                VALUES %s
                RETURNING id, station_code, distribution, method, frequency
                """,
                est_rows,
                fetch=True,
            )
        key_to_id: dict[tuple[str, str, str, str], int] = {
            (row[1], row[2], row[3], row[4]): row[0] for row in returned
        }

        # Map flow rows to the freshly created estimation IDs.
        flow_insert: list[tuple[Any, ...]] = []
        for sc, dist, meth, freq, rp, prob, q in flow_rows:
            est_id = key_to_id.get((sc, dist, meth, freq))
            if est_id is not None:
                flow_insert.append((est_id, rp, prob, q))

        if flow_insert:
            self._executemany(
                f"""
                INSERT INTO {self._s("estimated_flows")}
                    (estimation_id, return_period, probability, q_estimated_m3s)
                VALUES (%s, %s, %s, %s)
                """,
                flow_insert,
            )

        self.con.commit()
        return len(est_rows), len(flow_insert)
