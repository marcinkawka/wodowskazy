from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from modules import parser
from .models import Gauge
from .repository import (
    GaugeRepository,
    MeasurementRepository,
    PhenomenonRepository,
)


@dataclass
class ProcessResult:
    file: Path
    rows: int
    ok: bool
    error: str = ""


class HydroService:
    """
    Orchestrates parsing of CODZ/ZJAW files and persistence via repositories.
    """

    def __init__(
        self,
        gauge_repo: GaugeRepository,
        measurement_repo: MeasurementRepository,
        phenomenon_repo: PhenomenonRepository,
    ) -> None:
        self._gauges = gauge_repo
        self._measurements = measurement_repo
        self._phenomena = phenomenon_repo

    def _extract_gauges(self, df: pd.DataFrame) -> list[Gauge]:
        unique = df[["station_code", "station_name", "river_name"]].drop_duplicates(
            "station_code"
        )
        return [
            Gauge(
                station_code=row.station_code,
                station_name=row.station_name,
                river_name=row.river_name,
            )
            for row in unique.itertuples(index=False)
        ]

    def process_codz(self, path: Path) -> ProcessResult:
        try:
            df = parser.read_codz(path)
            if df.empty:
                return ProcessResult(file=path, rows=0, ok=True)

            self._gauges.upsert_many(self._extract_gauges(df))

            meas = df[[
                "station_code", "measured_at",
                "hydro_year", "hydro_month", "calendar_month",
                "water_level_cm", "flow_m3s", "water_temp_c",
            ]].copy()
            self._measurements.upsert_batch(meas)
            return ProcessResult(file=path, rows=len(meas), ok=True)

        except Exception as exc:
            return ProcessResult(file=path, rows=0, ok=False, error=str(exc))

    def process_zjaw(self, path: Path) -> ProcessResult:
        try:
            df = parser.read_zjaw(path)
            if df.empty:
                return ProcessResult(file=path, rows=0, ok=True)

            self._gauges.upsert_many(self._extract_gauges(df))

            phen = df[[
                "station_code", "measured_at", "hydro_year", "hydro_month",
                "ice_thickness_cm", "ice_phenomenon_code",
                "ice_phenomenon_pct", "overgrowth_code",
            ]].copy()
            self._phenomena.upsert_batch(phen)
            return ProcessResult(file=path, rows=len(phen), ok=True)

        except Exception as exc:
            return ProcessResult(file=path, rows=0, ok=False, error=str(exc))
