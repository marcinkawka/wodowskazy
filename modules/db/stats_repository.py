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
        station + calendar year + calendar month (from date).
        mes_count = number of daily records in the group.
        """
        # CTE isolates the aggregation scope — workaround for a DuckDB binder
        # bug where INSERT INTO target causes the target's column names to shadow
        # source columns (date becomes invisible) in GROUP BY resolution.
        self._con.execute("""
            WITH agg AS (
                SELECT
                    station_code,
                    CAST(EXTRACT(YEAR  FROM date) AS INTEGER) AS year,
                    CAST(EXTRACT(MONTH FROM date) AS INTEGER) AS month,
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
                GROUP BY
                    station_code,
                    EXTRACT(YEAR  FROM date),
                    EXTRACT(MONTH FROM date)
            )
            INSERT INTO stats_monthly SELECT * FROM agg
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
