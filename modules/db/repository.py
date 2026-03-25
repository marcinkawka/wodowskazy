import duckdb
import pandas as pd

from .models import Gauge


class GaugeRepository:
    """Persists and retrieves gauge (station) metadata."""

    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def upsert_many(self, gauges: list[Gauge]) -> None:
        if not gauges:
            return
        df = pd.DataFrame([
            {
                "station_code": g.station_code,
                "station_name": g.station_name,
                "river_name": g.river_name,
            }
            for g in gauges
        ])
        self._con.register("_gauges_tmp", df)
        self._con.execute("""
            INSERT INTO gauges_list (station_code, station_name, river_name)
            SELECT station_code, station_name, river_name
            FROM _gauges_tmp
            ON CONFLICT (station_code) DO NOTHING
        """)
        self._con.unregister("_gauges_tmp")

    def get_all(self) -> pd.DataFrame:
        return self._con.execute("SELECT * FROM gauges_list").df()


class MeasurementRepository:
    """Persists and retrieves daily water measurements (CODZ)."""

    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def upsert_batch(self, df: pd.DataFrame) -> None:
        if df.empty:
            return
        self._con.register("_meas_tmp", df)
        self._con.execute("""
            INSERT INTO measurements
            SELECT * FROM _meas_tmp
            ON CONFLICT (station_code, measured_at) DO UPDATE SET
                water_level_cm = excluded.water_level_cm,
                flow_m3s       = excluded.flow_m3s,
                water_temp_c   = excluded.water_temp_c
        """)
        self._con.unregister("_meas_tmp")

    def query_by_station(self, station_code: str) -> pd.DataFrame:
        return self._con.execute(
            "SELECT * FROM measurements"
            " WHERE station_code = ? ORDER BY measured_at",
            [station_code],
        ).df()


class PhenomenonRepository:
    """Persists and retrieves ice/vegetation phenomena (ZJAW)."""

    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def upsert_batch(self, df: pd.DataFrame) -> None:
        if df.empty:
            return
        self._con.register("_phen_tmp", df)
        self._con.execute("""
            INSERT INTO phenomena
            SELECT * FROM _phen_tmp
            ON CONFLICT (station_code, measured_at) DO UPDATE SET
                ice_thickness_cm    = excluded.ice_thickness_cm,
                ice_phenomenon_code = excluded.ice_phenomenon_code,
                ice_phenomenon_pct  = excluded.ice_phenomenon_pct,
                overgrowth_code     = excluded.overgrowth_code
        """)
        self._con.unregister("_phen_tmp")

    def query_by_station(self, station_code: str) -> pd.DataFrame:
        return self._con.execute(
            "SELECT * FROM phenomena"
            " WHERE station_code = ? ORDER BY measured_at",
            [station_code],
        ).df()
