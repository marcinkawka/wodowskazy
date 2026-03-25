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
                lon           DOUBLE
            )
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

    def close(self) -> None:
        self.con.close()
