from __future__ import annotations

from typing import Optional, Tuple
from pydantic import BaseModel
from datetime import datetime


class RouteRequest(BaseModel):
    start: Tuple[float, float]   # (lat, lng)
    end: Tuple[float, float]     # (lat, lng)
    datetime: Optional[datetime] = None


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
    cache_age_minutes: Optional[int] = None
