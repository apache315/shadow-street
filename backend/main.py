from __future__ import annotations

from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from models import HealthResponse
from osm_loader import load_walk_graph, load_buildings, load_trees, get_covered_edges
from shadow_engine import compute_shadow_weights
from cache import save_shadow_weights

_cache_age_minutes: Optional[int] = None
_G = None
_buildings = None
_trees = None
_covered_edges = None
scheduler = AsyncIOScheduler()


async def refresh_shadow_cache() -> None:
    global _cache_age_minutes
    now = datetime.now(timezone.utc)
    weights, _ = compute_shadow_weights(now, _G, _buildings, _trees, _covered_edges)
    save_shadow_weights(weights, now)
    _cache_age_minutes = 0


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
    return HealthResponse(status="ok", cache_age_minutes=_cache_age_minutes)
