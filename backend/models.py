from __future__ import annotations

from typing import Optional, Tuple
from pydantic import BaseModel
from datetime import datetime as _datetime


class RouteRequest(BaseModel):
    start: Tuple[float, float]   # (lat, lng)
    end: Tuple[float, float]     # (lat, lng)
    # NOTE: the field is intentionally still named `datetime` (the API
    # contract / request JSON key), but the imported type is aliased to
    # `_datetime` so the field name doesn't shadow the type during
    # annotation resolution (this module uses `from __future__ import
    # annotations`, so annotations are strings resolved lazily in this
    # module's namespace -- without the alias, the class attribute named
    # `datetime` shadows the imported `datetime` class, breaking every
    # request that actually supplies a custom datetime).
    datetime: Optional[_datetime] = None


class RouteInfo(BaseModel):
    geojson: dict
    total_distance_m: float
    total_duration_s: float
    shade_pct: float


class RouteResponse(BaseModel):
    fastest: RouteInfo
    shadiest: RouteInfo
    night: bool = False


class HealthResponse(BaseModel):
    status: str
    cache_age_minutes: Optional[int]
