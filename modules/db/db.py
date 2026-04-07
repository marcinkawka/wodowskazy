import duckdb


class Database:
    """
    Manages the DuckDB connection and schema lifecycle.
    Uses CREATE TABLE IF NOT EXISTS — safe to call on an existing database;
    existing data is preserved and only missing tables are created.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self.con: duckdb.DuckDBPyConnection = duckdb.connect(path)

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

    def close(self) -> None:
        self.con.close()
