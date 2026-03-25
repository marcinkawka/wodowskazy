"""
Statistics repository — computes and persists IMGW-notation hydro stats.

Notation:
  Q  = flow (flow_m3s)       W  = water level (water_level_cm)
  N  = min                   S  = mean (average)
  Z  = median                W prefix = max

Monthly / annual columns:  NQ  SQ  ZQ  WQ  NW  SW  ZW  WW  mes_count
All-time (from monthly):   NNQ  WWQ  SWQ  SNQ  SSQ  mes_count

All numeric values are rounded to 2 decimal places.
mes_count = number of source rows used to compute the statistics.
"""

import duckdb


class StatsRepository:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def compute_monthly(self) -> int:
        """
        Aggregate measurements into monthly statistics grouped by
        station + calendar year + calendar month (from measured_at).
        mes_count = number of daily records in the group.
        """
        self._con.execute("""
            INSERT INTO stats_monthly
            SELECT
                station_code,
                year(measured_at)                    AS year,
                month(measured_at)                   AS month,
                ROUND(MIN(flow_m3s),          2)     AS NQ,
                ROUND(AVG(flow_m3s),          2)     AS SQ,
                ROUND(MEDIAN(flow_m3s),       2)     AS ZQ,
                ROUND(MAX(flow_m3s),          2)     AS WQ,
                ROUND(MIN(water_level_cm),    2)     AS NW,
                ROUND(AVG(water_level_cm),    2)     AS SW,
                ROUND(MEDIAN(water_level_cm), 2)     AS ZW,
                ROUND(MAX(water_level_cm),    2)     AS WW,
                COUNT(*)                             AS mes_count
            FROM measurements
            GROUP BY station_code, year(measured_at), month(measured_at)
            ON CONFLICT (station_code, year, month) DO UPDATE SET
                NQ        = excluded.NQ,
                SQ        = excluded.SQ,
                ZQ        = excluded.ZQ,
                WQ        = excluded.WQ,
                NW        = excluded.NW,
                SW        = excluded.SW,
                ZW        = excluded.ZW,
                WW        = excluded.WW,
                mes_count = excluded.mes_count
        """)
        return self._con.execute("SELECT COUNT(*) FROM stats_monthly").fetchone()[0]

    def compute_annual(self) -> int:
        """
        Aggregate measurements into annual statistics using hydro_year.
        Polish hydrological year runs Nov 1 - Oct 31.
        mes_count = number of daily records in the hydrological year.
        """
        self._con.execute("""
            INSERT INTO stats_annual
            SELECT
                station_code,
                hydro_year,
                ROUND(MIN(flow_m3s),          2)     AS NQ,
                ROUND(AVG(flow_m3s),          2)     AS SQ,
                ROUND(MEDIAN(flow_m3s),       2)     AS ZQ,
                ROUND(MAX(flow_m3s),          2)     AS WQ,
                ROUND(MIN(water_level_cm),    2)     AS NW,
                ROUND(AVG(water_level_cm),    2)     AS SW,
                ROUND(MEDIAN(water_level_cm), 2)     AS ZW,
                ROUND(MAX(water_level_cm),    2)     AS WW,
                COUNT(*)                             AS mes_count
            FROM measurements
            WHERE hydro_year IS NOT NULL
            GROUP BY station_code, hydro_year
            ON CONFLICT (station_code, hydro_year) DO UPDATE SET
                NQ        = excluded.NQ,
                SQ        = excluded.SQ,
                ZQ        = excluded.ZQ,
                WQ        = excluded.WQ,
                NW        = excluded.NW,
                SW        = excluded.SW,
                ZW        = excluded.ZW,
                WW        = excluded.WW,
                mes_count = excluded.mes_count
        """)
        return self._con.execute("SELECT COUNT(*) FROM stats_annual").fetchone()[0]

    def compute_alltime(self) -> int:
        """
        Derive all-time characteristic flows from monthly statistics.
        Must be called after compute_monthly().

        NNQ = min(NQ)  — lowest recorded monthly minimum flow
        WWQ = max(WQ)  — highest recorded monthly maximum flow
        SWQ = avg(WQ)  — mean of monthly maxima
        SNQ = avg(NQ)  — mean of monthly minima
        SSQ = avg(SQ)  — mean of monthly means
        mes_count = number of monthly records used.
        """
        self._con.execute("""
            INSERT INTO stats_alltime
            SELECT
                station_code,
                ROUND(MIN(NQ),  2)   AS NNQ,
                ROUND(MAX(WQ),  2)   AS WWQ,
                ROUND(AVG(WQ),  2)   AS SWQ,
                ROUND(AVG(NQ),  2)   AS SNQ,
                ROUND(AVG(SQ),  2)   AS SSQ,
                COUNT(*)             AS mes_count
            FROM stats_monthly
            GROUP BY station_code
            ON CONFLICT (station_code) DO UPDATE SET
                NNQ       = excluded.NNQ,
                WWQ       = excluded.WWQ,
                SWQ       = excluded.SWQ,
                SNQ       = excluded.SNQ,
                SSQ       = excluded.SSQ,
                mes_count = excluded.mes_count
        """)
        return self._con.execute("SELECT COUNT(*) FROM stats_alltime").fetchone()[0]

    def query_monthly(self, station_code: str) -> list[tuple]:
        return self._con.execute(
            "SELECT * FROM stats_monthly WHERE station_code = ? ORDER BY year, month",
            [station_code],
        ).fetchall()

    def query_annual(self, station_code: str) -> list[tuple]:
        return self._con.execute(
            "SELECT * FROM stats_annual WHERE station_code = ? ORDER BY hydro_year",
            [station_code],
        ).fetchall()

    def query_alltime(self, station_code: str) -> tuple | None:
        return self._con.execute(
            "SELECT * FROM stats_alltime WHERE station_code = ?",
            [station_code],
        ).fetchone()
