from __future__ import annotations

from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from pysolar.solar import get_altitude

from models import HealthResponse, RouteRequest, RouteResponse, RouteInfo
from osm_loader import load_walk_graph, load_buildings, load_trees, get_covered_edges
from shadow_engine import compute_shadow_weights, PISA_LAT, PISA_LON
from cache import save_shadow_weights, load_shadow_weights
from router import find_routes

_cache_refreshed_at: Optional[datetime] = None
_G = None
_buildings = None
_trees = None
_covered_edges = None
scheduler = AsyncIOScheduler()


async def refresh_shadow_cache() -> None:
    global _cache_refreshed_at
    now = datetime.now(timezone.utc)
    weights, _ = compute_shadow_weights(now, _G, _buildings, _trees, _covered_edges)
    save_shadow_weights(weights, now)
    _cache_refreshed_at = now


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _G, _buildings, _trees, _covered_edges
    _G = load_walk_graph()
    _buildings = load_buildings()
    _trees = load_trees()
    _covered_edges = get_covered_edges(_G)
    await refresh_shadow_cache()
    scheduler.add_job(
        refresh_shadow_cache,
        CronTrigger(hour="7-21", minute="0,30", timezone="Europe/Rome"),
    )
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Shadow Street API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health():
    cache_age = (
        int((datetime.now(timezone.utc) - _cache_refreshed_at).total_seconds() // 60)
        if _cache_refreshed_at
        else None
    )
    return HealthResponse(status="ok", cache_age_minutes=cache_age)


@app.post("/route", response_model=RouteResponse)
async def route(req: RouteRequest):
    dt = req.datetime or datetime.now(timezone.utc)
    weights = load_shadow_weights(dt)
    if weights is None:
        raise HTTPException(
            status_code=503,
            detail="Shadow data not yet available for this time slot — try again shortly",
        )
    dt_aware = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    sun_alt = get_altitude(PISA_LAT, PISA_LON, dt_aware)
    night = sun_alt <= 0
    try:
        fastest_info, shadiest_info, night = find_routes(
            _G, req.start, req.end, weights, night=night
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return RouteResponse(
        fastest=RouteInfo(**fastest_info),
        shadiest=RouteInfo(**shadiest_info),
        night=night,
    )
