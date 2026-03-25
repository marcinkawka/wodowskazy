# 🌊 wodowskazy

> Polish river gauge data pipeline — from raw IMGW-PIB archives to a queryable local database.

A lightweight ETL pipeline that downloads, extracts, and parses **70+ years** of daily hydrological observations from Polish river gauges into a structured [DuckDB](https://duckdb.org/) database, ready for analysis.

---

## What's inside

- **866 monthly measurement files** (1951–2024) with daily water level, flow, and temperature
- **74 annual ice/vegetation phenomena files** tracking freeze events, ice cover, and river overgrowth
- **~250 gauge stations** across Poland with data going back to 1951
- Timestamps stored at **07:00 UTC** (the standard IMGW-PIB observation time)

---

## Data source

Data comes from **IMGW-PIB** (Institute of Meteorology and Water Management — _Instytut Meteorologii i Gospodarki Wodnej_), the Polish national meteorological and hydrological service. Files are published as part of their open data initiative.

Two file types are parsed:

| Type | File pattern | Contents |
|------|-------------|----------|
| CODZ | `codz_YYYY_MM.csv` | Water level [cm], flow [m³/s], temperature [°C] |
| ZJAW | `zjaw_YYYY.csv` | Ice thickness, ice phenomenon codes, overgrowth codes |

---

## Database schema

```
gauges_list              measurements                  phenomena
─────────────────        ──────────────────────────    ──────────────────────────
station_code  PK    ←──  station_code          FK  ←── station_code        FK
station_name             measured_at TIMESTAMPTZ       measured_at TIMESTAMPTZ
river_name               hydro_year                    hydro_year
lat                      hydro_month                   hydro_month
lon                      calendar_month                ice_thickness_cm
                         water_level_cm                ice_phenomenon_code
                         flow_m3s                      ice_phenomenon_pct
                         water_temp_c                  overgrowth_code
```

`measured_at` is stored as `TIMESTAMPTZ` at **07:00 UTC** (09:00 CET / 08:00 CEST).
`PRIMARY KEY (station_code, measured_at)` enforces one measurement per station per day.
Index on `station_code` for fast per-station queries.

---

## Quick start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager

### Setup

```bash
git clone <repo-url>
cd wodowskazy
uv sync
```

### 1 — Get the data

Download the IMGW-PIB hydrological archives and place them under `incoming_data/`:

```
incoming_data/
└── dane_hydrologiczne/
    └── dobowe/
        ├── 1951/
        │   ├── codz_1951_01.zip
        │   └── ...
        └── 2024/
            └── ...
```

### 2 — Extract archives

```bash
./scripts/extract_data.sh
```

This mirrors the directory structure from `incoming_data/` into `extracted_data/`, extracting all `.zip` files. Safe to re-run — existing files are not overwritten.

### 3 — Parse into DuckDB

```bash
# Quick test — first 10 files only
uv run python raw_data_parser.py

# Full load — all ~940 files
uv run python raw_data_parser.py --all
```

Output: `hydro.duckdb` in the project root.

---

## Query examples

```python
import duckdb

con = duckdb.connect("hydro.duckdb")

# Water levels for a specific station over time
con.execute("""
    SELECT measured_at, water_level_cm, flow_m3s
    FROM measurements
    WHERE station_code = '149180020'
    ORDER BY measured_at
""").df()

# Stations with the most ice events
con.execute("""
    SELECT g.station_name, g.river_name, COUNT(*) AS ice_days
    FROM phenomena p
    JOIN gauges_list g USING (station_code)
    WHERE ice_phenomenon_code IS NOT NULL
    GROUP BY 1, 2
    ORDER BY ice_days DESC
    LIMIT 10
""").df()

# Annual maximum flow per station
con.execute("""
    SELECT station_code, hydro_year, MAX(flow_m3s) AS peak_flow_m3s
    FROM measurements
    WHERE flow_m3s IS NOT NULL
    GROUP BY station_code, hydro_year
    ORDER BY peak_flow_m3s DESC
""").df()
```

---

## Project structure

```
wodowskazy/
├── scripts/
│   └── extract_data.sh       # zip extraction script
├── modules/
│   ├── parser.py             # CSV → DataFrame (encoding, nulls, timestamps)
│   └── db/
│       ├── __init__.py
│       ├── db.py             # Database connection + schema
│       ├── models.py         # Gauge dataclass
│       ├── repository.py     # GaugeRepository, MeasurementRepository, PhenomenonRepository
│       └── service.py        # HydroService — orchestrates parsing + persistence
├── raw_data_parser.py        # entry point
├── pyproject.toml
├── incoming_data/            # raw zip archives (not in git)
└── extracted_data/           # unzipped CSVs (not in git)
```

The data layer follows the **Service-Repository pattern**:

```
raw_data_parser.py
    └── HydroService
            ├── parser.read_codz / read_zjaw
            ├── GaugeRepository
            ├── MeasurementRepository
            └── PhenomenonRepository
```

---

## Notes

- **Encoding**: source files use `cp1250` (Windows Latin-2). The parser handles this transparently.
- **Null sentinels**: `9999` (level), `≥99999.999` (flow), `99.9` (temperature), `999` (ice thickness) are all converted to `NULL`.
- **Hydrological year**: runs November 1 – October 31. `hydro_month = 1` is November.
- **2023/2024 data**: IMGW-PIB changed the file format slightly (unquoted fields, annual instead of monthly files). The parser handles both formats.
- **Idempotent**: `create_schema()` uses `CREATE TABLE IF NOT EXISTS` and all inserts use `ON CONFLICT DO UPDATE` — re-running the parser against an existing database is safe.
- **DuckDB concurrency**: only one writer at a time. Close any open connections (e.g. DBeaver) before running the parser.

---

## License

Data © IMGW-PIB, published under their open data terms.
Code: MIT
