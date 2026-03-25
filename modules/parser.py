"""
CSV parsing for IMGW-PIB hydrological data files.

CODZ (daily measurements) columns — no header:
  station_code, station_name, river_name,
  hydro_year, hydro_month, day,
  water_level_cm, flow_m3s, water_temp_c, calendar_month

ZJAW (ice/vegetation phenomena) columns — no header:
  station_code, station_name, river_name,
  hydro_year, hydro_month, day,
  ice_thickness_cm, ice_phenomenon_code, ice_phenomenon_pct, overgrowth_code

Encoding: cp1250 (Windows Latin-2, used by IMGW-PIB).
Sentinel nulls: water_level=9999, flow>=99999.999, temp=99.9, ice=999.
Measurements are recorded daily at 07:00 UTC (9 CET / 8 CEST).
Note: 2023/2024 files have unquoted text fields (see UWAGA.txt).
"""

from pathlib import Path

import pandas as pd

ENCODING = "cp1250"
MEASUREMENT_HOUR_UTC = 7

_CODZ_COLS = [
    "station_code",
    "station_name",
    "river_name",
    "hydro_year",
    "hydro_month",
    "day",
    "water_level_cm",
    "flow_m3s",
    "water_temp_c",
    "calendar_month",
]

_ZJAW_COLS = [
    "station_code",
    "station_name",
    "river_name",
    "hydro_year",
    "hydro_month",
    "day",
    "ice_thickness_cm",
    "ice_phenomenon_code",
    "ice_phenomenon_pct",
    "overgrowth_code",
]


def _read_raw(path: Path, col_names: list[str]) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        header=None,
        names=col_names,
        encoding=ENCODING,
        encoding_errors="replace",
        dtype=str,
        on_bad_lines="skip",
    )
    for col in df.columns:
        df[col] = df[col].str.strip().str.strip('"').str.strip()
    return df


def _calendar_year(
    hydro_year: pd.Series,
    cal_month: pd.Series,
) -> pd.Series:
    """
    Polish hydrological year runs Nov 1 - Oct 31.
    Calendar months 11-12 belong to (hydro_year - 1).
    """
    return hydro_year.where(cal_month <= 10, hydro_year - 1)


def _build_timestamps(
    hydro_year: pd.Series,
    cal_month: pd.Series,
    day: pd.Series,
) -> pd.Series:
    """Return a UTC-aware timestamp series at 07:00 UTC for each row."""
    year = _calendar_year(hydro_year, cal_month)
    date_str = (
        year.astype(str)
        + "-"
        + cal_month.astype(str).str.zfill(2)
        + "-"
        + day.astype(str).str.zfill(2)
        + f" {MEASUREMENT_HOUR_UTC:02d}:00:00"
    )
    ts = pd.to_datetime(date_str, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    return ts.dt.tz_localize("UTC")


def _hydro_month_to_calendar(hydro_month: pd.Series) -> pd.Series:
    """hydro_month 1=Nov, 2=Dec, 3=Jan … 12=Oct → calendar month."""
    return ((hydro_month + 9) % 12) + 1


def read_codz(path: Path) -> pd.DataFrame:
    """
    Parse a CODZ CSV file into a DataFrame ready for the measurements table.
    Also includes station_name and river_name for gauge upserts.
    """
    df = _read_raw(path, _CODZ_COLS)
    if df.empty:
        return df

    df["hydro_year"] = pd.to_numeric(df["hydro_year"], errors="coerce")
    df["hydro_month"] = pd.to_numeric(df["hydro_month"], errors="coerce")
    df["day"] = pd.to_numeric(df["day"], errors="coerce")
    df = df.dropna(subset=["hydro_year", "hydro_month", "day"])

    df["calendar_month"] = pd.to_numeric(df["calendar_month"], errors="coerce")
    missing = df["calendar_month"].isna()
    if missing.any():
        df.loc[missing, "calendar_month"] = _hydro_month_to_calendar(df.loc[missing, "hydro_month"])

    df["measured_at"] = _build_timestamps(df["hydro_year"], df["calendar_month"], df["day"])
    df = df.dropna(subset=["measured_at"])

    df["water_level_cm"] = pd.to_numeric(df["water_level_cm"], errors="coerce")
    df["flow_m3s"] = pd.to_numeric(df["flow_m3s"], errors="coerce")
    df["water_temp_c"] = pd.to_numeric(df["water_temp_c"], errors="coerce")

    df.loc[df["water_level_cm"] == 9999, "water_level_cm"] = pd.NA
    df.loc[df["flow_m3s"] >= 99999.999, "flow_m3s"] = pd.NA
    df.loc[df["water_temp_c"] == 99.9, "water_temp_c"] = pd.NA

    df["hydro_year"] = df["hydro_year"].astype("Int64")
    df["hydro_month"] = df["hydro_month"].astype("Int64")
    df["calendar_month"] = df["calendar_month"].astype("Int64")
    df["water_level_cm"] = df["water_level_cm"].astype("Int64")

    return df


def read_zjaw(path: Path) -> pd.DataFrame:
    """
    Parse a ZJAW CSV file into a DataFrame ready for the phenomena table.
    ZJAW files have no calendar_month — it is derived from hydro_month.
    """
    df = _read_raw(path, _ZJAW_COLS)
    if df.empty:
        return df

    df["hydro_year"] = pd.to_numeric(df["hydro_year"], errors="coerce")
    df["hydro_month"] = pd.to_numeric(df["hydro_month"], errors="coerce")
    df["day"] = pd.to_numeric(df["day"], errors="coerce")
    df = df.dropna(subset=["hydro_year", "hydro_month", "day"])

    cal_month = _hydro_month_to_calendar(df["hydro_month"])
    df["measured_at"] = _build_timestamps(df["hydro_year"], cal_month, df["day"])
    df = df.dropna(subset=["measured_at"])

    df["ice_thickness_cm"] = pd.to_numeric(df["ice_thickness_cm"], errors="coerce")
    df["ice_phenomenon_pct"] = pd.to_numeric(df["ice_phenomenon_pct"], errors="coerce")
    df.loc[df["ice_thickness_cm"] == 999, "ice_thickness_cm"] = pd.NA
    df["ice_phenomenon_code"] = df["ice_phenomenon_code"].replace("", pd.NA)
    df["overgrowth_code"] = df["overgrowth_code"].replace("", pd.NA)

    df["hydro_year"] = df["hydro_year"].astype("Int64")
    df["hydro_month"] = df["hydro_month"].astype("Int64")
    df["ice_thickness_cm"] = df["ice_thickness_cm"].astype("Int64")
    df["ice_phenomenon_pct"] = df["ice_phenomenon_pct"].astype("Int64")

    return df
