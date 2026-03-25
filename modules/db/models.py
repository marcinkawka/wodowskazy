from dataclasses import dataclass, field


@dataclass
class Gauge:
    station_code: str
    station_name: str
    river_name: str
    lat: float | None = field(default=None)
    lon: float | None = field(default=None)
