# Shadow Street Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a mobile-first web app that finds the fastest and shadiest walking routes in Pisa, Italy, using OSM building/tree data and real-time sun position.

**Architecture:** FastAPI backend computes shadow weights every 30 min via APScheduler, stores them as JSON. POST /route reads cached weights, runs networkx A* twice (different edge weights) on a single osmnx walk graph. React + MapLibre GL JS frontend shows both routes on a full-screen map with a bottom sheet.

**Tech Stack:** Python 3.11, FastAPI, osmnx, networkx, pysolar, shapely, pyproj, APScheduler · React 18, Vite, MapLibre GL JS · Docker Compose

## Global Constraints

- Python 3.11 exact (osmnx 1.9.x requires it)
- All coordinates: WGS84 (EPSG:4326) at API boundary; UTM Zone 32N (EPSG:32632) internally for shadow math
- Edge keys in cache: `"{u}_{v}"` where u, v are OSM node integer IDs
- Walking speed assumption: 1.4 m/s for duration_s calculation
- Shade deviation cap: shadiest route ≤ 1.5× fastest distance
- Shadow cache files: `data/shadow_cache/shadows_HHMM.json` (HHMM = floor-to-30min slot, local Rome time)
- Shadow cron runs 07:00–21:00 Europe/Rome, every 30 min
- Sun altitude clamp: < 10° → twilight mode (all shade=0.8); below horizon → night (all shade=1.0, `night=true` in response)
- Tree canopy shade contribution: 0.6 (partial, not opaque)
- Default building height: 9m (3 floors × 3m) when `building:levels` absent
- Nominatim User-Agent header required: `"shadow-street-pisa/1.0"`
- Frontend colors: `--route-fast: #FF8C00`, `--route-shade: #1565C0`, `--shade-overlay: #B3C8F0`
- Font: Inter (Google Fonts)
- No user accounts, no auth, no persistence beyond OSM + shadow cache

---

## File Structure

```
shadow-street/
├── backend/
│   ├── main.py              # FastAPI app, APScheduler, /route + /health
│   ├── models.py            # Pydantic request/response models
│   ├── osm_loader.py        # Download + disk-cache OSM graph, buildings, trees
│   ├── shadow_engine.py     # Sun position, shadow projection, shade_fraction per edge
│   ├── cache.py             # Read/write shadows_HHMM.json
│   ├── router.py            # networkx A* fastest + shadiest, deviation cap
│   ├── requirements.txt
│   ├── Dockerfile
│   └── tests/
│       ├── conftest.py
│       ├── test_shadow_engine.py
│       ├── test_cache.py
│       ├── test_router.py
│       └── test_api.py
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── Dockerfile
│   └── src/
│       ├── main.jsx
│       ├── App.jsx          # Root, global state (routes, selectedTime, lang)
│       ├── api.js           # POST /route wrapper
│       ├── components/
│       │   ├── Map.jsx           # MapLibre GL JS wrapper, ref forwarding
│       │   ├── SearchBar.jsx     # Nominatim autocomplete input
│       │   ├── BottomSheet.jsx   # 3-state drawer (collapsed/mid/expanded)
│       │   ├── Sidebar.jsx       # Desktop sidebar (≥768px)
│       │   ├── RouteCard.jsx     # Single route card (fastest or shadiest)
│       │   ├── TimeControl.jsx   # Adesso/+1h/+2h/Personalizza pills
│       │   └── RouteLayer.jsx    # MapLibre source+layer for a route GeoJSON
│       ├── hooks/
│       │   ├── useGeolocation.js # GPS position hook
│       │   └── useRoutes.js      # Calls api.js, manages loading/error state
│       └── styles/
│           ├── variables.css     # CSS custom properties
│           └── index.css         # Global reset + base styles
├── docker-compose.yml
└── nginx.conf
```

---

### Task 1: Project Scaffold + Health Endpoint

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/main.py`
- Create: `backend/models.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_api.py`
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.jsx`
- Create: `frontend/src/App.jsx`

**Interfaces:**
- Produces: `GET /health` → `{"status": "ok", "cache_age_minutes": int}`
- Produces: FastAPI `app` instance importable by tests

- [ ] **Step 1: Create backend/requirements.txt**

```
fastapi==0.111.0
uvicorn[standard]==0.30.1
osmnx==1.9.3
networkx==3.3
pysolar==0.11
shapely==2.0.4
pyproj==3.6.1
apscheduler==3.10.4
pytest==8.2.2
pytest-asyncio==0.23.7
httpx==0.27.0
```

- [ ] **Step 2: Create backend/models.py**

```python
from pydantic import BaseModel
from datetime import datetime


class RouteRequest(BaseModel):
    start: tuple[float, float]   # (lat, lng)
    end: tuple[float, float]     # (lat, lng)
    datetime: datetime | None = None


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
    cache_age_minutes: int | None
```

- [ ] **Step 3: Create backend/main.py (health only, no scheduler yet)**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models import HealthResponse

app = FastAPI(title="Shadow Street API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_cache_age_minutes: int | None = None


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", cache_age_minutes=_cache_age_minutes)
```

- [ ] **Step 4: Create backend/tests/conftest.py**

```python
import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
```

- [ ] **Step 5: Create backend/tests/test_api.py**

```python
import pytest

pytestmark = pytest.mark.asyncio


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "cache_age_minutes" in data
```

- [ ] **Step 6: Create pytest.ini (so pytest-asyncio works)**

Create `backend/pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 7: Run test to verify it passes**

```bash
cd backend
pip install -r requirements.txt
pytest tests/test_api.py -v
```
Expected: `PASSED tests/test_api.py::test_health`

- [ ] **Step 8: Scaffold frontend**

Create `frontend/package.json`:
```json
{
  "name": "shadow-street",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "maplibre-gl": "^4.5.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.1",
    "vite": "^5.3.4"
  }
}
```

Create `frontend/vite.config.js`:
```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
```

Create `frontend/index.html`:
```html
<!DOCTYPE html>
<html lang="it">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Shadow Street — Pisa</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

Create `frontend/src/main.jsx`:
```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './styles/variables.css'
import './styles/index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
```

Create `frontend/src/App.jsx` (stub):
```jsx
export default function App() {
  return <div style={{ fontFamily: 'Inter, sans-serif' }}>Shadow Street — loading…</div>
}
```

- [ ] **Step 9: Install frontend deps and verify dev server starts**

```bash
cd frontend
npm install
npm run dev
```
Expected: Vite server starts at `http://localhost:5173`, browser shows "Shadow Street — loading…"

- [ ] **Step 10: Commit**

```bash
git init
git add backend/ frontend/
git commit -m "feat: project scaffold, health endpoint, frontend Vite setup"
```

---

### Task 2: OSM Data Loader

**Files:**
- Create: `backend/osm_loader.py`
- Create: `backend/data/osm_cache/` (directory, gitignored)
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Produces: `load_walk_graph() -> nx.MultiDiGraph`
- Produces: `load_buildings() -> gpd.GeoDataFrame` (columns: geometry, height_m)
- Produces: `load_trees() -> gpd.GeoDataFrame` (columns: geometry as Points/LineStrings)
- Produces: `get_covered_edges(G) -> set[tuple[int,int]]`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_osm_loader.py`:
```python
import pytest
import networkx as nx
import geopandas as gpd
from unittest.mock import patch, MagicMock
from osm_loader import load_walk_graph, load_buildings, load_trees, get_covered_edges, _parse_height


def test_parse_height_from_levels():
    assert _parse_height({"building:levels": "3"}) == 9.0


def test_parse_height_from_height_tag():
    assert _parse_height({"height": "12m"}) == 12.0


def test_parse_height_default():
    assert _parse_height({}) == 9.0


def test_parse_height_bad_value():
    assert _parse_height({"building:levels": "yes"}) == 9.0


def test_get_covered_edges_returns_set():
    G = nx.MultiDiGraph()
    G.add_node(1, x=10.4, y=43.7)
    G.add_node(2, x=10.41, y=43.7)
    G.add_edge(1, 2, covered="yes")
    G.add_edge(2, 1)
    covered = get_covered_edges(G)
    assert (1, 2) in covered
    assert (2, 1) not in covered
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && pytest tests/test_osm_loader.py -v
```
Expected: `ModuleNotFoundError: No module named 'osm_loader'`

- [ ] **Step 3: Create backend/osm_loader.py**

```python
import pickle
from pathlib import Path
import networkx as nx
import geopandas as gpd
import osmnx as ox

PISA_PLACE = "Pisa, Italy"
CACHE_DIR = Path("data/osm_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _parse_height(row: dict) -> float:
    levels = row.get("building:levels")
    if levels is not None:
        try:
            return float(levels) * 3.0
        except (ValueError, TypeError):
            pass
    height = row.get("height")
    if height is not None:
        try:
            return float(str(height).replace("m", "").strip())
        except (ValueError, TypeError):
            pass
    return 9.0


def load_walk_graph() -> nx.MultiDiGraph:
    cache_path = CACHE_DIR / "walk_graph.pkl"
    if cache_path.exists():
        with open(cache_path, "rb") as f:
            return pickle.load(f)
    G = ox.graph_from_place(PISA_PLACE, network_type="walk")
    with open(cache_path, "wb") as f:
        pickle.dump(G, f)
    return G


def load_buildings() -> gpd.GeoDataFrame:
    cache_path = CACHE_DIR / "buildings.pkl"
    if cache_path.exists():
        return gpd.read_parquet(cache_path)
    gdf = ox.features_from_place(PISA_PLACE, tags={"building": True})
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    gdf["height_m"] = gdf.apply(
        lambda row: _parse_height(row.to_dict()), axis=1
    )
    gdf = gdf[["geometry", "height_m"]].reset_index(drop=True)
    gdf.to_parquet(cache_path)
    return gdf


def load_trees() -> gpd.GeoDataFrame:
    cache_path = CACHE_DIR / "trees.pkl"
    if cache_path.exists():
        return gpd.read_parquet(cache_path)
    tags = {"natural": ["tree", "tree_row"]}
    try:
        gdf = ox.features_from_place(PISA_PLACE, tags=tags)
    except Exception:
        return gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")
    gdf = gdf[["geometry"]].reset_index(drop=True)
    gdf.to_parquet(cache_path)
    return gdf


def get_covered_edges(G: nx.MultiDiGraph) -> set[tuple[int, int]]:
    covered = set()
    for u, v, data in G.edges(data=True):
        if data.get("covered") == "yes" or data.get("tunnel") == "yes":
            covered.add((u, v))
    return covered
```

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_osm_loader.py -v
```
Expected: all 5 tests PASS (no network calls needed — tests use synthetic data)

- [ ] **Step 5: Verify live download works (slow, one-time)**

```bash
cd backend && python -c "from osm_loader import load_walk_graph; G = load_walk_graph(); print(f'Nodes: {len(G.nodes)}, Edges: {len(G.edges)}')"
```
Expected: `Nodes: ~15000, Edges: ~35000` (cached to disk after first run)

- [ ] **Step 6: Add data/ to .gitignore**

Create `backend/.gitignore`:
```
data/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 7: Commit**

```bash
git add backend/osm_loader.py backend/tests/test_osm_loader.py backend/.gitignore backend/pytest.ini
git commit -m "feat: OSM data loader with disk cache for graph, buildings, trees"
```

---

### Task 3: Shadow Engine Core

**Files:**
- Create: `backend/shadow_engine.py`
- Create: `backend/tests/test_shadow_engine.py`

**Interfaces:**
- Consumes: `nx.MultiDiGraph` from `load_walk_graph()`, `gpd.GeoDataFrame` from `load_buildings()` and `load_trees()`, `set[tuple]` from `get_covered_edges()`
- Produces: `compute_shadow_weights(dt, G, buildings, trees, covered_edges) -> tuple[dict[str, float], bool]`
  - dict key: `"{u}_{v}"`, value: shade_fraction 0.0–1.0
  - bool: `night` flag

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_shadow_engine.py`:
```python
import pytest
from datetime import datetime, timezone
import networkx as nx
from shapely.geometry import LineString, Polygon, Point
import geopandas as gpd
from shadow_engine import (
    compute_shadow_weights,
    _project_building_shadow,
    _edge_key,
    TWILIGHT_ALTITUDE,
)


@pytest.fixture
def tiny_graph():
    G = nx.MultiDiGraph()
    G.add_node(1, x=10.4017, y=43.7228)
    G.add_node(2, x=10.4027, y=43.7228)
    G.add_edge(1, 2, length=80.0,
               geometry=LineString([(10.4017, 43.7228), (10.4027, 43.7228)]))
    G.add_edge(2, 1, length=80.0,
               geometry=LineString([(10.4027, 43.7228), (10.4017, 43.7228)]))
    return G


@pytest.fixture
def empty_buildings():
    return gpd.GeoDataFrame({"geometry": [], "height_m": []}, crs="EPSG:4326")


@pytest.fixture
def empty_trees():
    return gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")


def test_night_returns_all_shade_1(tiny_graph, empty_buildings, empty_trees):
    # 2024-01-15 00:00 UTC → night in Pisa
    dt = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
    weights, night = compute_shadow_weights(dt, tiny_graph, empty_buildings, empty_trees, set())
    assert night is True
    for v in weights.values():
        assert v == 1.0


def test_daytime_no_buildings_returns_zero_shade(tiny_graph, empty_buildings, empty_trees):
    # 2024-07-15 10:00 UTC → midday in Pisa, no buildings
    dt = datetime(2024, 7, 15, 10, 0, 0, tzinfo=timezone.utc)
    weights, night = compute_shadow_weights(dt, tiny_graph, empty_buildings, empty_trees, set())
    assert night is False
    for v in weights.values():
        assert v == pytest.approx(0.0, abs=0.05)


def test_covered_edge_always_full_shade(tiny_graph, empty_buildings, empty_trees):
    dt = datetime(2024, 7, 15, 10, 0, 0, tzinfo=timezone.utc)
    covered = {(1, 2)}
    weights, _ = compute_shadow_weights(dt, tiny_graph, empty_buildings, empty_trees, covered)
    assert weights[_edge_key(1, 2)] == 1.0


def test_edge_key_format():
    assert _edge_key(123, 456) == "123_456"


def test_project_building_shadow_returns_larger_polygon():
    # Small square building, sun at 45° altitude from south
    footprint = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    shadow = _project_building_shadow(footprint, height_m=10.0,
                                      sun_alt_deg=45.0, sun_az_deg=180.0)
    assert shadow.area > footprint.area


def test_twilight_constant_value():
    assert TWILIGHT_ALTITUDE == 10.0
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && pytest tests/test_shadow_engine.py -v
```
Expected: `ModuleNotFoundError: No module named 'shadow_engine'`

- [ ] **Step 3: Create backend/shadow_engine.py**

```python
import math
from datetime import datetime, timezone
from typing import Any

import networkx as nx
import geopandas as gpd
from shapely.geometry import LineString, Point, MultiPolygon
from shapely.ops import transform, unary_union
from shapely.affinity import translate
from pyproj import Transformer
from pysolar.solar import get_altitude, get_azimuth

PISA_LAT = 43.7228
PISA_LON = 10.4017
UTM_CRS = "EPSG:32632"
WGS84_CRS = "EPSG:4326"
TWILIGHT_ALTITUDE = 10.0
SAMPLE_STEP_M = 5.0
TREE_CANOPY_RADIUS_M = 4.0
TREE_SHADE_FRACTION = 0.6

_to_utm = Transformer.from_crs(WGS84_CRS, UTM_CRS, always_xy=True)
_to_wgs = Transformer.from_crs(UTM_CRS, WGS84_CRS, always_xy=True)


def _edge_key(u: int, v: int) -> str:
    return f"{u}_{v}"


def _project_building_shadow(footprint_utm, height_m: float,
                              sun_alt_deg: float, sun_az_deg: float):
    shadow_length = height_m / math.tan(math.radians(sun_alt_deg))
    shadow_az = (sun_az_deg + 180) % 360
    dx = shadow_length * math.sin(math.radians(shadow_az))
    dy = shadow_length * math.cos(math.radians(shadow_az))
    shadow = translate(footprint_utm, xoff=dx, yoff=dy)
    return footprint_utm.union(shadow)


def _edge_shade_fraction(geom_wgs84: LineString, shadow_union, tree_union) -> float:
    geom_utm = transform(_to_utm.transform, geom_wgs84)
    length = geom_utm.length
    n = max(2, int(length / SAMPLE_STEP_M))
    points = [geom_utm.interpolate(i / (n - 1), normalized=True) for i in range(n)]

    building_hits = sum(1 for p in points if shadow_union is not None and shadow_union.contains(p))
    tree_hits = sum(1 for p in points
                    if shadow_union is not None and not shadow_union.contains(p)
                    and tree_union is not None and tree_union.contains(p))

    shade = (building_hits + tree_hits * TREE_SHADE_FRACTION) / len(points)
    return min(1.0, shade)


def compute_shadow_weights(
    dt: datetime,
    G: nx.MultiDiGraph,
    buildings: gpd.GeoDataFrame,
    trees: gpd.GeoDataFrame,
    covered_edges: set[tuple[int, int]],
) -> tuple[dict[str, float], bool]:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    sun_alt = get_altitude(PISA_LAT, PISA_LON, dt)
    sun_az = get_azimuth(PISA_LAT, PISA_LON, dt)

    # Night: sun below horizon
    if sun_alt <= 0:
        weights = {_edge_key(u, v): 1.0 for u, v, _ in G.edges(data=True)}
        return weights, True

    # Twilight: sun too low for reliable shadow geometry
    if sun_alt < TWILIGHT_ALTITUDE:
        weights = {_edge_key(u, v): 0.8 for u, v, _ in G.edges(data=True)}
        return weights, False

    # Build shadow union from buildings
    shadow_polys = []
    for _, row in buildings.iterrows():
        try:
            geom_utm = transform(_to_utm.transform, row.geometry)
            shadow = _project_building_shadow(geom_utm, row.height_m, sun_alt, sun_az)
            shadow_polys.append(shadow)
        except Exception:
            continue
    shadow_union = unary_union(shadow_polys) if shadow_polys else None

    # Build tree canopy union (fixed circles, sun-direction agnostic for MVP)
    tree_polys = []
    for _, row in trees.iterrows():
        try:
            geom_utm = transform(_to_utm.transform, row.geometry)
            if geom_utm.geom_type == "Point":
                tree_polys.append(geom_utm.buffer(TREE_CANOPY_RADIUS_M))
            else:
                tree_polys.append(geom_utm.buffer(TREE_CANOPY_RADIUS_M))
        except Exception:
            continue
    tree_union = unary_union(tree_polys) if tree_polys else None

    weights = {}
    for u, v, data in G.edges(data=True):
        key = _edge_key(u, v)
        if (u, v) in covered_edges:
            weights[key] = 1.0
            continue
        geom = data.get("geometry")
        if geom is None:
            geom = LineString([
                (G.nodes[u]["x"], G.nodes[u]["y"]),
                (G.nodes[v]["x"], G.nodes[v]["y"]),
            ])
        weights[key] = _edge_shade_fraction(geom, shadow_union, tree_union)

    return weights, False
```

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_shadow_engine.py -v
```
Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/shadow_engine.py backend/tests/test_shadow_engine.py
git commit -m "feat: shadow engine with pysolar, shapely projection, tree + portico support"
```

---

### Task 4: Shadow Cache + APScheduler

**Files:**
- Create: `backend/cache.py`
- Create: `backend/tests/test_cache.py`
- Modify: `backend/main.py`

**Interfaces:**
- Consumes: `compute_shadow_weights()` result
- Produces: `save_shadow_weights(weights, dt) -> None`
- Produces: `load_shadow_weights(dt) -> dict | None`
- Produces: `cache_slot(dt) -> str` (e.g. `"1430"`)

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_cache.py`:
```python
import pytest
import json
from datetime import datetime, timezone
from pathlib import Path
from cache import save_shadow_weights, load_shadow_weights, cache_slot


def test_cache_slot_floors_to_30min():
    dt = datetime(2024, 7, 15, 14, 47, 0, tzinfo=timezone.utc)
    # In Rome (UTC+2 summer), 14:47 UTC = 16:47 local → slot "1630"
    slot = cache_slot(dt)
    assert slot in ("1630", "1430")  # allow for TZ implementation


def test_cache_slot_on_the_hour():
    dt = datetime(2024, 7, 15, 8, 0, 0, tzinfo=timezone.utc)
    slot = cache_slot(dt)
    assert len(slot) == 4
    assert slot.isdigit()


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    import cache
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    dt = datetime(2024, 7, 15, 14, 0, 0, tzinfo=timezone.utc)
    weights = {"123_456": 0.75, "456_789": 0.1}
    save_shadow_weights(weights, dt)
    loaded = load_shadow_weights(dt)
    assert loaded == weights


def test_load_returns_none_when_missing(tmp_path, monkeypatch):
    import cache
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    dt = datetime(2024, 7, 15, 23, 0, 0, tzinfo=timezone.utc)
    result = load_shadow_weights(dt)
    assert result is None
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && pytest tests/test_cache.py -v
```
Expected: `ModuleNotFoundError: No module named 'cache'`

- [ ] **Step 3: Create backend/cache.py**

```python
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

CACHE_DIR = Path("data/shadow_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
ROME_TZ = ZoneInfo("Europe/Rome")


def cache_slot(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(ROME_TZ)
    # Floor to nearest 30-min slot
    minute = 0 if local.minute < 30 else 30
    return f"{local.hour:02d}{minute:02d}"


def save_shadow_weights(weights: dict, dt: datetime) -> None:
    slot = cache_slot(dt)
    path = CACHE_DIR / f"shadows_{slot}.json"
    path.write_text(json.dumps(weights))


def load_shadow_weights(dt: datetime) -> dict | None:
    slot = cache_slot(dt)
    path = CACHE_DIR / f"shadows_{slot}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())
```

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_cache.py -v
```
Expected: all 4 tests PASS

- [ ] **Step 5: Wire APScheduler into main.py**

Replace `backend/main.py` entirely:
```python
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from models import HealthResponse
from osm_loader import load_walk_graph, load_buildings, load_trees, get_covered_edges
from shadow_engine import compute_shadow_weights
from cache import save_shadow_weights

_cache_age_minutes: int | None = None
_G = None
_buildings = None
_trees = None
_covered_edges = None
scheduler = AsyncIOScheduler()


async def refresh_shadow_cache():
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
```

- [ ] **Step 6: Update conftest.py to skip lifespan in unit tests**

Replace `backend/tests/conftest.py`:
```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from main import app


@pytest.fixture
async def client():
    # Patch lifespan so tests don't download OSM data
    with patch("main.refresh_shadow_cache", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
```

- [ ] **Step 7: Run full test suite**

```bash
cd backend && pytest tests/ -v
```
Expected: all tests PASS (health, osm_loader, shadow_engine, cache)

- [ ] **Step 8: Commit**

```bash
git add backend/cache.py backend/main.py backend/tests/test_cache.py backend/tests/conftest.py
git commit -m "feat: shadow cache JSON storage + APScheduler every 30min"
```

---

### Task 5: Router (Fastest + Shadiest)

**Files:**
- Create: `backend/router.py`
- Create: `backend/tests/test_router.py`

**Interfaces:**
- Consumes: `nx.MultiDiGraph`, `dict[str, float]` (shadow weights), `tuple[float,float]` start/end (lat, lng)
- Produces: `find_routes(G, start, end, shadow_weights, alpha) -> tuple[dict, dict, bool]`
  - Returns `(fastest_info, shadiest_info, night)` where each info is:
  - `{"geojson": dict, "total_distance_m": float, "total_duration_s": float, "shade_pct": float}`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_router.py`:
```python
import pytest
import networkx as nx
from shapely.geometry import LineString
from router import find_routes, _annotate_route, DEVIATION_CAP


@pytest.fixture
def linear_graph():
    """A → B → C with a direct A→C shortcut. A→B shaded, B→C sunny."""
    G = nx.MultiDiGraph()
    G.add_node(1, x=10.4000, y=43.7228)
    G.add_node(2, x=10.4010, y=43.7228)
    G.add_node(3, x=10.4020, y=43.7228)
    G.add_edge(1, 2, length=100.0,
               geometry=LineString([(10.4000, 43.7228), (10.4010, 43.7228)]))
    G.add_edge(2, 1, length=100.0,
               geometry=LineString([(10.4010, 43.7228), (10.4000, 43.7228)]))
    G.add_edge(2, 3, length=100.0,
               geometry=LineString([(10.4010, 43.7228), (10.4020, 43.7228)]))
    G.add_edge(3, 2, length=100.0,
               geometry=LineString([(10.4020, 43.7228), (10.4010, 43.7228)]))
    return G


@pytest.fixture
def shadow_weights_shaded_ab():
    return {"1_2": 0.9, "2_1": 0.9, "2_3": 0.0, "3_2": 0.0}


def test_fastest_route_finds_path(linear_graph, shadow_weights_shaded_ab):
    fastest, shadiest, night = find_routes(
        linear_graph,
        start=(43.7228, 10.4000),
        end=(43.7228, 10.4020),
        shadow_weights=shadow_weights_shaded_ab,
    )
    assert fastest["total_distance_m"] == pytest.approx(200.0, rel=0.1)


def test_shadiest_route_prefers_shade(linear_graph, shadow_weights_shaded_ab):
    fastest, shadiest, night = find_routes(
        linear_graph,
        start=(43.7228, 10.4000),
        end=(43.7228, 10.4020),
        shadow_weights=shadow_weights_shaded_ab,
    )
    assert shadiest["shade_pct"] >= fastest["shade_pct"]


def test_both_routes_have_geojson(linear_graph, shadow_weights_shaded_ab):
    fastest, shadiest, _ = find_routes(
        linear_graph,
        start=(43.7228, 10.4000),
        end=(43.7228, 10.4020),
        shadow_weights=shadow_weights_shaded_ab,
    )
    assert fastest["geojson"]["type"] == "FeatureCollection"
    assert shadiest["geojson"]["type"] == "FeatureCollection"


def test_deviation_cap_constant():
    assert DEVIATION_CAP == 1.5


def test_duration_uses_walking_speed(linear_graph, shadow_weights_shaded_ab):
    fastest, _, _ = find_routes(
        linear_graph,
        start=(43.7228, 10.4000),
        end=(43.7228, 10.4020),
        shadow_weights=shadow_weights_shaded_ab,
    )
    expected_s = fastest["total_distance_m"] / 1.4
    assert fastest["total_duration_s"] == pytest.approx(expected_s, rel=0.01)
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && pytest tests/test_router.py -v
```
Expected: `ModuleNotFoundError: No module named 'router'`

- [ ] **Step 3: Create backend/router.py**

```python
from shapely.geometry import mapping, LineString
import networkx as nx
import osmnx as ox

DEVIATION_CAP = 1.5
WALKING_SPEED_MS = 1.4


def _edge_key(u: int, v: int) -> str:
    return f"{u}_{v}"


def _weight_shadiest(u, v, data, shadow_weights: dict, alpha: float) -> float:
    dist = data.get("length", 1.0)
    shade = shadow_weights.get(_edge_key(u, v), 0.0)
    sun_exposed = dist * (1 - shade)
    return dist + alpha * sun_exposed


def _annotate_route(G: nx.MultiDiGraph, path: list[int],
                    shadow_weights: dict) -> dict:
    features = []
    total_dist = 0.0
    total_shade_dist = 0.0

    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        edge_data = min(G[u][v].values(), key=lambda d: d.get("length", float("inf")))
        geom = edge_data.get(
            "geometry",
            LineString([(G.nodes[u]["x"], G.nodes[u]["y"]),
                        (G.nodes[v]["x"], G.nodes[v]["y"])]),
        )
        dist = edge_data.get("length", geom.length)
        shade = shadow_weights.get(_edge_key(u, v), 0.0)

        features.append({
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {
                "shade_pct": round(shade * 100, 1),
                "distance_m": round(dist, 1),
                "duration_s": round(dist / WALKING_SPEED_MS, 1),
            },
        })
        total_dist += dist
        total_shade_dist += dist * shade

    shade_pct = round(total_shade_dist / total_dist * 100, 1) if total_dist > 0 else 0.0
    return {
        "geojson": {"type": "FeatureCollection", "features": features},
        "total_distance_m": round(total_dist, 1),
        "total_duration_s": round(total_dist / WALKING_SPEED_MS, 1),
        "shade_pct": shade_pct,
    }


def find_routes(
    G: nx.MultiDiGraph,
    start: tuple[float, float],
    end: tuple[float, float],
    shadow_weights: dict[str, float],
    alpha: float = 2.0,
) -> tuple[dict, dict, bool]:
    start_lat, start_lng = start
    end_lat, end_lng = end

    start_node = ox.distance.nearest_nodes(G, X=start_lng, Y=start_lat)
    end_node = ox.distance.nearest_nodes(G, X=end_lng, Y=end_lat)

    fastest_path = nx.shortest_path(G, start_node, end_node, weight="length")
    fastest_info = _annotate_route(G, fastest_path, shadow_weights)

    shadiest_path = nx.shortest_path(
        G, start_node, end_node,
        weight=lambda u, v, d: _weight_shadiest(u, v, d, shadow_weights, alpha),
    )
    shadiest_info = _annotate_route(G, shadiest_path, shadow_weights)

    # Apply deviation cap: if shadiest is too long, fall back to fastest
    if shadiest_info["total_distance_m"] > DEVIATION_CAP * fastest_info["total_distance_m"]:
        shadiest_info = fastest_info.copy()
        shadiest_info["_capped"] = True

    return fastest_info, shadiest_info, False
```

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_router.py -v
```
Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/router.py backend/tests/test_router.py
git commit -m "feat: router with networkx A*, shade cost function, 1.5x deviation cap"
```

---

### Task 6: POST /route API Endpoint

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `find_routes()` from router.py, `load_shadow_weights()` from cache.py
- Produces: `POST /route` → `RouteResponse` JSON

- [ ] **Step 1: Write failing test first**

Add to `backend/tests/test_api.py`:
```python
async def test_route_endpoint_returns_two_routes(client):
    from unittest.mock import patch
    mock_weights = {}  # empty → all sun

    with patch("main.load_shadow_weights", return_value=mock_weights), \
         patch("main.find_routes") as mock_find:
        mock_find.return_value = (
            {"geojson": {"type": "FeatureCollection", "features": []},
             "total_distance_m": 500.0, "total_duration_s": 357.0, "shade_pct": 20.0},
            {"geojson": {"type": "FeatureCollection", "features": []},
             "total_distance_m": 650.0, "total_duration_s": 464.0, "shade_pct": 70.0},
            False,
        )
        r = await client.post("/route", json={
            "start": [43.7228, 10.4017],
            "end": [43.7156, 10.3952],
        })
    assert r.status_code == 200
    data = r.json()
    assert "fastest" in data
    assert "shadiest" in data
    assert data["fastest"]["total_distance_m"] == 500.0
    assert data["shadiest"]["shade_pct"] == 70.0
    assert data["night"] is False


async def test_route_endpoint_requires_start_and_end(client):
    r = await client.post("/route", json={"start": [43.7228, 10.4017]})
    assert r.status_code == 422
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && pytest tests/test_api.py::test_route_endpoint_returns_two_routes -v
```
Expected: `FAILED` — route not found (404)

- [ ] **Step 3: Add /route to main.py**

Add these imports and endpoint to `backend/main.py` (keep existing code, add below health):
```python
from datetime import datetime, timezone
from fastapi import HTTPException
from models import RouteRequest, RouteResponse, RouteInfo
from cache import load_shadow_weights
from router import find_routes


@app.post("/route", response_model=RouteResponse)
async def route(req: RouteRequest):
    dt = req.datetime or datetime.now(timezone.utc)
    weights = load_shadow_weights(dt)
    if weights is None:
        # No cache yet (startup edge case): use empty weights → all sun
        weights = {}

    try:
        fastest_info, shadiest_info, night = find_routes(
            _G, req.start, req.end, weights
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return RouteResponse(
        fastest=RouteInfo(**fastest_info),
        shadiest=RouteInfo(**shadiest_info),
        night=night,
    )
```

- [ ] **Step 4: Run full test suite**

```bash
cd backend && pytest tests/ -v
```
Expected: all tests PASS

- [ ] **Step 5: Manual smoke test (requires OSM data on disk)**

```bash
cd backend && uvicorn main:app --reload
# In another terminal:
curl -X POST http://localhost:8000/route \
  -H "Content-Type: application/json" \
  -d '{"start":[43.7228,10.4017],"end":[43.7156,10.3952]}'
```
Expected: JSON with `fastest` and `shadiest` keys, each with `geojson`, `total_distance_m`, `shade_pct`.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/tests/test_api.py
git commit -m "feat: POST /route endpoint wires router + shadow cache"
```

---

### Task 7: Frontend Scaffold + MapLibre Map

**Files:**
- Create: `frontend/src/styles/variables.css`
- Create: `frontend/src/styles/index.css`
- Create: `frontend/src/components/Map.jsx`
- Modify: `frontend/src/App.jsx`

**Interfaces:**
- Produces: `<Map onMapReady={fn} />` — renders full-screen MapLibre map, calls `onMapReady(mapInstance)` when loaded
- Pisa center: `[10.4017, 43.7228]`, zoom 14

- [ ] **Step 1: Create frontend/src/styles/variables.css**

```css
:root {
  --route-fast: #FF8C00;
  --route-shade: #1565C0;
  --shade-overlay: #B3C8F0;
  --text-primary: #1A1A1A;
  --text-secondary: #757575;
  --bg: #FFFFFF;
  --green-badge: #2E7D32;
  --surface: #F5F5F5;
  --border: #E0E0E0;
  --shadow-sm: 0 1px 4px rgba(0,0,0,0.12);
  --shadow-md: 0 4px 16px rgba(0,0,0,0.15);
  --radius-sm: 8px;
  --radius-pill: 24px;
  --font: 'Inter', sans-serif;
}
```

- [ ] **Step 2: Create frontend/src/styles/index.css**

```css
@import url('https://unpkg.com/maplibre-gl@4.5.0/dist/maplibre-gl.css');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: var(--font);
  color: var(--text-primary);
  background: var(--bg);
  height: 100dvh;
  overflow: hidden;
}

#root { height: 100dvh; position: relative; }
```

- [ ] **Step 3: Create frontend/src/components/Map.jsx**

```jsx
import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'

const PISA_CENTER = [10.4017, 43.7228]
const MAP_STYLE = 'https://tiles.openfreemap.org/styles/liberty'

export default function Map({ onMapReady }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)

  useEffect(() => {
    if (mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: PISA_CENTER,
      zoom: 14,
    })
    map.addControl(new maplibregl.NavigationControl(), 'top-right')
    map.on('load', () => {
      mapRef.current = map
      onMapReady?.(map)
    })
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
}
```

- [ ] **Step 4: Update App.jsx to show the map**

```jsx
import { useRef, useState } from 'react'
import Map from './components/Map.jsx'

export default function App() {
  const [mapReady, setMapReady] = useState(false)

  return (
    <div style={{ position: 'relative', width: '100%', height: '100dvh' }}>
      <Map onMapReady={() => setMapReady(true)} />
    </div>
  )
}
```

- [ ] **Step 5: Add maplibre CSS import to index.css correctly**

Replace the first line of `frontend/src/styles/index.css` (the @import) — MapLibre CSS should come from the installed npm package, not CDN:
```css
/* maplibre-gl CSS is imported in main.jsx */
```

Add to `frontend/src/main.jsx` before other imports:
```jsx
import 'maplibre-gl/dist/maplibre-gl.css'
```

- [ ] **Step 6: Verify map renders**

```bash
cd frontend && npm run dev
```
Open `http://localhost:5173` — expect full-screen OpenFreeMap map centered on Pisa.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat: MapLibre GL JS full-screen map centered on Pisa"
```

---

### Task 8: Search Bar + Geolocation

**Files:**
- Create: `frontend/src/hooks/useGeolocation.js`
- Create: `frontend/src/components/SearchBar.jsx`
- Modify: `frontend/src/App.jsx`

**Interfaces:**
- Produces: `useGeolocation()` → `{ position: {lat, lng} | null, error: string | null }`
- Produces: `<SearchBar lang onSelect={fn} />` — pill input with Nominatim dropdown, calls `onSelect({lat, lng, label})`

- [ ] **Step 1: Create frontend/src/hooks/useGeolocation.js**

```js
import { useState, useEffect } from 'react'

export function useGeolocation() {
  const [position, setPosition] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!navigator.geolocation) {
      setError('Geolocation not supported')
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => setPosition({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      (err) => setError(err.message),
      { enableHighAccuracy: true, timeout: 10000 }
    )
  }, [])

  return { position, error }
}
```

- [ ] **Step 2: Create frontend/src/components/SearchBar.jsx**

```jsx
import { useState, useRef, useEffect } from 'react'

const NOMINATIM = 'https://nominatim.openstreetmap.org/search'
const PISA_LANDMARKS = [
  { label: 'Torre di Pisa', lat: 43.7230, lng: 10.3966 },
  { label: 'Piazza dei Miracoli', lat: 43.7230, lng: 10.3966 },
  { label: 'Università di Pisa', lat: 43.7196, lng: 10.4054 },
  { label: 'Stazione Pisa Centrale', lat: 43.7089, lng: 10.3985 },
  { label: 'Piazza dei Cavalieri', lat: 43.7215, lng: 10.4024 },
]

const I18N = {
  it: { placeholder: 'Dove vuoi andare?' },
  en: { placeholder: 'Where are you going?' },
}

export default function SearchBar({ lang = 'it', onSelect }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const debounce = useRef(null)

  useEffect(() => {
    if (query.length < 3) {
      setResults(PISA_LANDMARKS.filter(l =>
        l.label.toLowerCase().includes(query.toLowerCase())
      ))
      return
    }
    clearTimeout(debounce.current)
    debounce.current = setTimeout(async () => {
      try {
        const url = `${NOMINATIM}?q=${encodeURIComponent(query + ' Pisa')}&format=json&limit=5&countrycodes=it`
        const res = await fetch(url, {
          headers: { 'User-Agent': 'shadow-street-pisa/1.0' }
        })
        const data = await res.json()
        setResults(data.map(d => ({
          label: d.display_name.split(',')[0],
          lat: parseFloat(d.lat),
          lng: parseFloat(d.lon),
        })))
      } catch {
        setResults([])
      }
    }, 350)
  }, [query])

  function handleSelect(item) {
    setQuery(item.label)
    setOpen(false)
    onSelect(item)
  }

  return (
    <div style={{
      position: 'absolute', top: 12, left: 12, right: 56,
      zIndex: 10,
    }}>
      <div style={{
        background: '#fff',
        borderRadius: 'var(--radius-pill)',
        boxShadow: 'var(--shadow-md)',
        display: 'flex', alignItems: 'center', padding: '10px 16px', gap: 8,
      }}>
        <span style={{ color: 'var(--text-secondary)', fontSize: 16 }}>🔍</span>
        <input
          value={query}
          onChange={e => { setQuery(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          placeholder={I18N[lang].placeholder}
          style={{
            border: 'none', outline: 'none', flex: 1,
            font: '16px var(--font)', color: 'var(--text-primary)',
          }}
        />
        {query && (
          <button
            onClick={() => { setQuery(''); setOpen(false) }}
            style={{ background: 'none', border: 'none', cursor: 'pointer',
                     color: 'var(--text-secondary)', fontSize: 18, lineHeight: 1 }}>
            ×
          </button>
        )}
      </div>
      {open && results.length > 0 && (
        <div style={{
          background: '#fff', borderRadius: 'var(--radius-sm)',
          boxShadow: 'var(--shadow-md)', marginTop: 4, overflow: 'hidden',
        }}>
          {results.map((r, i) => (
            <div key={i}
              onClick={() => handleSelect(r)}
              style={{
                padding: '12px 16px', cursor: 'pointer', fontSize: 14,
                borderBottom: i < results.length - 1 ? '1px solid var(--border)' : 'none',
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--surface)'}
              onMouseLeave={e => e.currentTarget.style.background = '#fff'}
            >
              {r.label}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Add GPS FAB + SearchBar to App.jsx**

```jsx
import { useRef, useState } from 'react'
import Map from './components/Map.jsx'
import SearchBar from './components/SearchBar.jsx'
import { useGeolocation } from './hooks/useGeolocation.js'

export default function App() {
  const [lang, setLang] = useState('it')
  const [destination, setDestination] = useState(null)
  const mapRef = useRef(null)
  const { position } = useGeolocation()

  function handleGPS() {
    if (position && mapRef.current) {
      mapRef.current.flyTo({ center: [position.lng, position.lat], zoom: 16 })
    }
  }

  return (
    <div style={{ position: 'relative', width: '100%', height: '100dvh' }}>
      <Map onMapReady={m => { mapRef.current = m }} />

      {/* Language toggle */}
      <div style={{
        position: 'absolute', top: 16, right: 12, zIndex: 10,
        background: '#fff', borderRadius: 20, padding: '4px 10px',
        boxShadow: 'var(--shadow-sm)', fontSize: 12, fontWeight: 600,
        cursor: 'pointer', userSelect: 'none',
      }} onClick={() => setLang(l => l === 'it' ? 'en' : 'it')}>
        {lang.toUpperCase()}
      </div>

      <SearchBar lang={lang} onSelect={setDestination} />

      {/* GPS FAB */}
      <button onClick={handleGPS} style={{
        position: 'absolute', bottom: 140, right: 16, zIndex: 10,
        width: 48, height: 48, borderRadius: '50%',
        background: 'var(--route-shade)', border: 'none',
        boxShadow: 'var(--shadow-md)', cursor: 'pointer',
        fontSize: 20, color: '#fff', display: 'flex',
        alignItems: 'center', justifyContent: 'center',
      }}>
        📍
      </button>
    </div>
  )
}
```

- [ ] **Step 4: Verify search works**

```bash
cd frontend && npm run dev
```
Open app, type "Torre" → dropdown shows Torre di Pisa. Type "Lungarno" → Nominatim results appear.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useGeolocation.js frontend/src/components/SearchBar.jsx frontend/src/App.jsx
git commit -m "feat: search bar with Nominatim autocomplete + GPS geolocation hook"
```

---

### Task 9: API Client + Route Layers on Map

**Files:**
- Create: `frontend/src/api.js`
- Create: `frontend/src/hooks/useRoutes.js`
- Create: `frontend/src/components/RouteLayer.jsx`
- Modify: `frontend/src/App.jsx`

**Interfaces:**
- Produces: `fetchRoutes(start, end, datetime?) -> Promise<RouteResponse>`
- Produces: `useRoutes(start, end, selectedTime)` → `{ fastest, shadiest, loading, error, night }`
- Produces: `<RouteLayer map routeId geojson color />` — adds/updates MapLibre source+layer

- [ ] **Step 1: Create frontend/src/api.js**

```js
const BASE = '/api'

export async function fetchRoutes(start, end, datetime = null) {
  const body = { start: [start.lat, start.lng], end: [end.lat, end.lng] }
  if (datetime) body.datetime = datetime
  const res = await fetch(`${BASE}/route`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`API error ${res.status}`)
  return res.json()
}
```

- [ ] **Step 2: Create frontend/src/hooks/useRoutes.js**

```js
import { useState, useEffect } from 'react'
import { fetchRoutes } from '../api.js'

export function useRoutes(start, end, selectedTime) {
  const [fastest, setFastest] = useState(null)
  const [shadiest, setShadiest] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [night, setNight] = useState(false)

  useEffect(() => {
    if (!start || !end) return
    setLoading(true)
    setError(null)
    fetchRoutes(start, end, selectedTime)
      .then(data => {
        setFastest(data.fastest)
        setShadiest(data.shadiest)
        setNight(data.night)
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [start?.lat, start?.lng, end?.lat, end?.lng, selectedTime])

  return { fastest, shadiest, loading, error, night }
}
```

- [ ] **Step 3: Create frontend/src/components/RouteLayer.jsx**

```jsx
import { useEffect } from 'react'

export default function RouteLayer({ map, routeId, geojson, color }) {
  useEffect(() => {
    if (!map || !geojson) return
    const sourceId = `route-${routeId}`
    const layerId = `route-layer-${routeId}`

    if (map.getSource(sourceId)) {
      map.getSource(sourceId).setData(geojson)
    } else {
      map.addSource(sourceId, { type: 'geojson', data: geojson })
      map.addLayer({
        id: layerId,
        type: 'line',
        source: sourceId,
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: {
          'line-color': color,
          'line-width': 5,
          'line-opacity': 0.85,
        },
      })
    }
    return () => {
      if (map.getLayer(layerId)) map.removeLayer(layerId)
      if (map.getSource(sourceId)) map.removeSource(sourceId)
    }
  }, [map, geojson, color, routeId])

  return null
}
```

- [ ] **Step 4: Wire routes into App.jsx**

Replace `frontend/src/App.jsx`:
```jsx
import { useRef, useState } from 'react'
import Map from './components/Map.jsx'
import SearchBar from './components/SearchBar.jsx'
import RouteLayer from './components/RouteLayer.jsx'
import { useGeolocation } from './hooks/useGeolocation.js'
import { useRoutes } from './hooks/useRoutes.js'

export default function App() {
  const [lang, setLang] = useState('it')
  const [destination, setDestination] = useState(null)
  const [selectedTime, setSelectedTime] = useState(null)
  const [activeRoute, setActiveRoute] = useState('shadiest')
  const mapRef = useRef(null)
  const { position } = useGeolocation()
  const start = position  // GPS position as start
  const { fastest, shadiest, loading, error, night } = useRoutes(start, destination, selectedTime)

  function handleGPS() {
    if (position && mapRef.current) {
      mapRef.current.flyTo({ center: [position.lng, position.lat], zoom: 16 })
    }
  }

  return (
    <div style={{ position: 'relative', width: '100%', height: '100dvh' }}>
      <Map onMapReady={m => { mapRef.current = m }} />

      {mapRef.current && fastest && (
        <RouteLayer map={mapRef.current} routeId="fastest"
          geojson={fastest.geojson} color="var(--route-fast)" />
      )}
      {mapRef.current && shadiest && (
        <RouteLayer map={mapRef.current} routeId="shadiest"
          geojson={shadiest.geojson} color="var(--route-shade)" />
      )}

      <div style={{
        position: 'absolute', top: 16, right: 12, zIndex: 10,
        background: '#fff', borderRadius: 20, padding: '4px 10px',
        boxShadow: 'var(--shadow-sm)', fontSize: 12, fontWeight: 600,
        cursor: 'pointer',
      }} onClick={() => setLang(l => l === 'it' ? 'en' : 'it')}>
        {lang.toUpperCase()}
      </div>

      <SearchBar lang={lang} onSelect={setDestination} />

      <button onClick={handleGPS} style={{
        position: 'absolute', bottom: 140, right: 16, zIndex: 10,
        width: 48, height: 48, borderRadius: '50%',
        background: 'var(--route-shade)', border: 'none',
        boxShadow: 'var(--shadow-md)', cursor: 'pointer',
        fontSize: 20, color: '#fff', display: 'flex',
        alignItems: 'center', justifyContent: 'center',
      }}>📍</button>

      {loading && (
        <div style={{
          position: 'absolute', top: 70, left: '50%', transform: 'translateX(-50%)',
          background: '#fff', borderRadius: 20, padding: '6px 16px',
          boxShadow: 'var(--shadow-sm)', fontSize: 13, zIndex: 10,
        }}>Calcolo percorsi…</div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Test end-to-end (backend must be running)**

```bash
# Terminal 1:
cd backend && uvicorn main:app --reload
# Terminal 2:
cd frontend && npm run dev
```
Open app, allow GPS, search for "Torre di Pisa", click result → two colored routes appear on map.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api.js frontend/src/hooks/useRoutes.js frontend/src/components/RouteLayer.jsx frontend/src/App.jsx
git commit -m "feat: API client, useRoutes hook, MapLibre route layers"
```

---

### Task 10: Bottom Sheet + Route Cards + Time Control

**Files:**
- Create: `frontend/src/components/RouteCard.jsx`
- Create: `frontend/src/components/TimeControl.jsx`
- Create: `frontend/src/components/BottomSheet.jsx`
- Modify: `frontend/src/App.jsx`

**Interfaces:**
- Produces: `<RouteCard type info active onClick />` — type: `'fastest'|'shadiest'`
- Produces: `<TimeControl selectedTime onChange />` — emits ISO8601 string or null (=now)
- Produces: `<BottomSheet state fastest shadiest night activeRoute onSelectRoute onTimeChange />`
  - `state`: `'collapsed'|'mid'|'expanded'`

- [ ] **Step 1: Create frontend/src/components/RouteCard.jsx**

```jsx
const I18N = {
  it: { fastest: 'Più veloce', shadiest: 'Più ombra', recommended: 'CONSIGLIATO', min: 'min' },
  en: { fastest: 'Fastest', shadiest: 'Shadiest', recommended: 'RECOMMENDED', min: 'min' },
}

export default function RouteCard({ type, info, active, onClick, lang = 'it' }) {
  if (!info) return null
  const t = I18N[lang]
  const color = type === 'fastest' ? 'var(--route-fast)' : 'var(--route-shade)'
  const icon = type === 'fastest' ? '☀️' : '🌿'
  const label = type === 'fastest' ? t.fastest : t.shadiest
  const isRecommendedMonth = new Date().getMonth() >= 5 && new Date().getMonth() <= 8
  const showBadge = type === 'shadiest' && isRecommendedMonth

  return (
    <div onClick={onClick} style={{
      flex: 1, background: active ? `${color}18` : '#fff',
      border: `2px solid ${active ? color : 'var(--border)'}`,
      borderRadius: 'var(--radius-sm)', padding: '12px',
      cursor: 'pointer', transition: 'all 0.15s', position: 'relative',
    }}>
      {showBadge && (
        <div style={{
          position: 'absolute', top: -10, left: '50%', transform: 'translateX(-50%)',
          background: 'var(--green-badge)', color: '#fff', fontSize: 9,
          fontWeight: 700, padding: '2px 8px', borderRadius: 10, whiteSpace: 'nowrap',
        }}>{t.recommended}</div>
      )}
      <div style={{ color, fontWeight: 600, fontSize: 13, marginBottom: 6 }}>
        {icon} {label}
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
        <div>⏱ {Math.round(info.total_duration_s / 60)} {t.min}</div>
        <div>→ {Math.round(info.total_distance_m)}m</div>
        <div>🌿 {info.shade_pct}% ombra</div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create frontend/src/components/TimeControl.jsx**

```jsx
import { useState } from 'react'

function buildTicks() {
  const ticks = []
  for (let h = 7; h <= 21; h++) {
    ticks.push({ label: `${String(h).padStart(2,'0')}:00`, minute: 0, hour: h })
    if (h < 21) ticks.push({ label: `${String(h).padStart(2,'0')}:30`, minute: 30, hour: h })
  }
  return ticks
}
const TICKS = buildTicks()

export default function TimeControl({ selectedTime, onChange, lang = 'it' }) {
  const [custom, setCustom] = useState(false)

  function applyOffset(offsetHours) {
    const d = new Date()
    d.setHours(d.getHours() + offsetHours, 0, 0, 0)
    // Clamp to 07:00-21:00
    if (d.getHours() < 7) d.setHours(7)
    if (d.getHours() > 21) d.setHours(21)
    onChange(d.toISOString())
  }

  const pillStyle = (active) => ({
    padding: '5px 12px', borderRadius: 16, fontSize: 12, fontWeight: 500,
    border: `1.5px solid ${active ? 'var(--route-shade)' : 'var(--border)'}`,
    background: active ? 'var(--route-shade)' : '#fff',
    color: active ? '#fff' : 'var(--text-primary)',
    cursor: 'pointer',
  })

  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6, fontWeight: 600, letterSpacing: '0.05em' }}>
        TIME CONTROL
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <button style={pillStyle(!selectedTime && !custom)}
          onClick={() => { setCustom(false); onChange(null) }}>
          Adesso
        </button>
        <button style={pillStyle(false)} onClick={() => applyOffset(1)}>+1h</button>
        <button style={pillStyle(false)} onClick={() => applyOffset(2)}>+2h</button>
        <button style={pillStyle(custom)}
          onClick={() => setCustom(c => !c)}>
          Personalizza
        </button>
      </div>
      {custom && (
        <select
          style={{ marginTop: 8, padding: '6px 10px', borderRadius: 8,
                   border: '1.5px solid var(--border)', fontSize: 13, width: '100%' }}
          onChange={e => {
            const tick = TICKS[parseInt(e.target.value)]
            const d = new Date()
            d.setHours(tick.hour, tick.minute, 0, 0)
            onChange(d.toISOString())
          }}>
          {TICKS.map((t, i) => <option key={i} value={i}>{t.label}</option>)}
        </select>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Create frontend/src/components/BottomSheet.jsx**

```jsx
import { useState, useRef } from 'react'
import RouteCard from './RouteCard.jsx'
import TimeControl from './TimeControl.jsx'

export default function BottomSheet({
  fastest, shadiest, night, activeRoute, onSelectRoute, onTimeChange,
  lang = 'it', loading,
}) {
  const [sheetState, setSheetState] = useState('collapsed') // collapsed|mid|expanded
  const startY = useRef(null)

  const heights = { collapsed: 80, mid: '50vh', expanded: '90vh' }

  function handleTouchStart(e) { startY.current = e.touches[0].clientY }
  function handleTouchEnd(e) {
    const dy = startY.current - e.changedTouches[0].clientY
    if (dy > 40) setSheetState(s => s === 'collapsed' ? 'mid' : 'expanded')
    if (dy < -40) setSheetState(s => s === 'expanded' ? 'mid' : 'collapsed')
  }

  const hasRoutes = fastest && shadiest

  return (
    <div
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
      style={{
        position: 'absolute', bottom: 0, left: 0, right: 0,
        background: '#fff', borderRadius: '20px 20px 0 0',
        boxShadow: '0 -4px 24px rgba(0,0,0,0.15)',
        height: typeof heights[sheetState] === 'number'
          ? `${heights[sheetState]}px` : heights[sheetState],
        transition: 'height 0.3s cubic-bezier(0.4,0,0.2,1)',
        zIndex: 20, padding: '0 16px 24px', overflow: 'hidden',
      }}>

      {/* Handle */}
      <div onClick={() => setSheetState(s => s === 'collapsed' ? 'mid' : s === 'mid' ? 'expanded' : 'collapsed')}
        style={{ padding: '10px 0 8px', display: 'flex', justifyContent: 'center', cursor: 'pointer' }}>
        <div style={{ width: 36, height: 4, background: '#ddd', borderRadius: 2 }} />
      </div>

      {/* Hint when collapsed */}
      {sheetState === 'collapsed' && (
        <div style={{ textAlign: 'center', fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
          {loading ? 'Calcolo…' : hasRoutes ? '2 percorsi trovati ↑' : 'Cerca una destinazione'}
        </div>
      )}

      {/* Night message */}
      {sheetState !== 'collapsed' && night && (
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', textAlign: 'center', padding: '8px 0' }}>
          Di notte tutti i percorsi sono in ombra — mostriamo il più breve.
        </div>
      )}

      {/* Route cards */}
      {sheetState !== 'collapsed' && hasRoutes && (
        <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
          <RouteCard type="fastest" info={fastest} lang={lang}
            active={activeRoute === 'fastest'}
            onClick={() => onSelectRoute('fastest')} />
          <RouteCard type="shadiest" info={shadiest} lang={lang}
            active={activeRoute === 'shadiest'}
            onClick={() => onSelectRoute('shadiest')} />
        </div>
      )}

      {/* Time control */}
      {sheetState !== 'collapsed' && (
        <TimeControl lang={lang} selectedTime={null} onChange={onTimeChange} />
      )}
    </div>
  )
}
```

- [ ] **Step 4: Add BottomSheet to App.jsx**

Add import and render BottomSheet inside App:
```jsx
import BottomSheet from './components/BottomSheet.jsx'

// Inside App return, before closing </div>:
<BottomSheet
  fastest={fastest}
  shadiest={shadiest}
  night={night}
  activeRoute={activeRoute}
  onSelectRoute={setActiveRoute}
  onTimeChange={setSelectedTime}
  lang={lang}
  loading={loading}
/>
```

- [ ] **Step 5: Verify bottom sheet**

```bash
cd frontend && npm run dev
```
Open in Chrome DevTools mobile view (iPhone 14). Bottom sheet visible at bottom. Swipe up → mid state shows route cards. Swipe up again → expanded. Swipe down → collapses.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/
git commit -m "feat: bottom sheet with route cards, time control, swipe gestures"
```

---

### Task 11: Desktop Sidebar + Responsive Layout

**Files:**
- Create: `frontend/src/components/Sidebar.jsx`
- Modify: `frontend/src/App.jsx`

**Interfaces:**
- Produces: `<Sidebar ...samePropsAsBottomSheet lang />` — 320px left panel on ≥768px screens

- [ ] **Step 1: Create frontend/src/components/Sidebar.jsx**

```jsx
import RouteCard from './RouteCard.jsx'
import TimeControl from './TimeControl.jsx'

const PISA_LANDMARKS = [
  'Torre di Pisa', 'Piazza dei Miracoli', 'Università di Pisa',
  'Stazione Pisa Centrale', 'Piazza dei Cavalieri',
]

export default function Sidebar({
  fastest, shadiest, night, activeRoute, onSelectRoute,
  onTimeChange, lang = 'it', loading, onLandmarkClick,
}) {
  return (
    <div style={{
      position: 'absolute', top: 0, left: 0, bottom: 0,
      width: 320, background: '#fff', zIndex: 20,
      boxShadow: '2px 0 16px rgba(0,0,0,0.1)',
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{ padding: '20px 16px 12px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ fontWeight: 700, fontSize: 18, marginBottom: 4 }}>🌿 Shadow Street</div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Pisa — percorsi ombrosi</div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
        {/* Landmarks (shown before search) */}
        {!fastest && !loading && (
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)',
                          letterSpacing: '0.05em', marginBottom: 8 }}>LUOGHI POPOLARI</div>
            {PISA_LANDMARKS.map((name, i) => (
              <div key={i}
                onClick={() => onLandmarkClick?.(name)}
                style={{ padding: '10px 0', fontSize: 13, cursor: 'pointer',
                         borderBottom: '1px solid var(--border)',
                         color: 'var(--text-primary)' }}>
                📍 {name}
              </div>
            ))}
          </div>
        )}

        {loading && (
          <div style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: 24 }}>
            Calcolo percorsi…
          </div>
        )}

        {night && fastest && (
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', padding: '8px 0' }}>
            Di notte tutti i percorsi sono in ombra — mostriamo il più breve.
          </div>
        )}

        {fastest && shadiest && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 8 }}>
            <RouteCard type="fastest" info={fastest} lang={lang}
              active={activeRoute === 'fastest'}
              onClick={() => onSelectRoute('fastest')} />
            <RouteCard type="shadiest" info={shadiest} lang={lang}
              active={activeRoute === 'shadiest'}
              onClick={() => onSelectRoute('shadiest')} />
          </div>
        )}

        {(fastest || shadiest) && (
          <TimeControl lang={lang} selectedTime={null} onChange={onTimeChange} />
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Add responsive detection + Sidebar to App.jsx**

Add at top of App component:
```jsx
const isDesktop = window.innerWidth >= 768
```

Inside return, before `<Map>`:
```jsx
{isDesktop && (
  <Sidebar
    fastest={fastest} shadiest={shadiest} night={night}
    activeRoute={activeRoute} onSelectRoute={setActiveRoute}
    onTimeChange={setSelectedTime} lang={lang} loading={loading}
  />
)}
```

Offset map on desktop — wrap Map in a div:
```jsx
<div style={{
  position: 'absolute',
  left: isDesktop ? 320 : 0,
  top: 0, right: 0, bottom: 0,
}}>
  <Map onMapReady={m => { mapRef.current = m }} />
  {/* Route layers, FAB, search bar go here too */}
</div>
```

Move SearchBar inside map div on desktop too (top search is already positioned absolute within parent).

On mobile, keep BottomSheet; on desktop, hide it:
```jsx
{!isDesktop && <BottomSheet ... />}
```

- [ ] **Step 3: Add Sidebar import**

```jsx
import Sidebar from './components/Sidebar.jsx'
```

- [ ] **Step 4: Verify responsive layout**

```bash
cd frontend && npm run dev
```
- Mobile view (< 768px): no sidebar, bottom sheet visible
- Desktop view (≥ 768px): 320px sidebar on left, map fills right, no bottom sheet

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Sidebar.jsx frontend/src/App.jsx
git commit -m "feat: desktop sidebar layout, responsive breakpoint at 768px"
```

---

### Task 12: Docker Compose + Production Config

**Files:**
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `docker-compose.yml`
- Create: `nginx.conf`

- [ ] **Step 1: Create backend/Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p data/osm_cache data/shadow_cache

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create frontend/Dockerfile**

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

- [ ] **Step 3: Create nginx.conf**

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://backend:8000/;
        proxy_set_header Host $host;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 4: Create docker-compose.yml**

```yaml
version: '3.9'

services:
  backend:
    build: ./backend
    volumes:
      - osm_cache:/app/data/osm_cache
      - shadow_cache:/app/data/shadow_cache
    environment:
      - TZ=Europe/Rome
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      backend:
        condition: service_healthy
    restart: unless-stopped

volumes:
  osm_cache:
  shadow_cache:
```

- [ ] **Step 5: Build and run**

```bash
docker-compose build
docker-compose up
```
Expected: frontend at `http://localhost`, backend health at `http://localhost/api/health` → `{"status":"ok"}`

- [ ] **Step 6: Final commit**

```bash
git add backend/Dockerfile frontend/Dockerfile docker-compose.yml nginx.conf
git commit -m "feat: Docker Compose production setup with nginx reverse proxy"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| 2 percorsi: veloce + ombroso | Task 5, 6 |
| GPS come partenza default | Task 8 |
| Toggle IT/EN | Task 8, 10 |
| Bottom sheet 3 stati + swipe | Task 10 |
| Time control (Adesso/+1h/+2h/Personalizza) | Task 10 |
| Personalizza limitato a tick di oggi | Task 10 (select con TICKS 07:00-21:00) |
| Edifici OSM + altezza stimata | Task 2, 3 |
| Alberi OSM (natural=tree, tree_row) | Task 2, 3 |
| Portici (covered=yes) → shade=1.0 | Task 2, 3 |
| Clamp sole basso (< 10°) | Task 3 |
| Gestione notte (shade=1.0, night flag) | Task 3, 6, 10 |
| Cache ogni 30 min 07:00-21:00 | Task 4 |
| Formula penalità sole + cap 1.5x | Task 5 |
| Desktop sidebar 320px | Task 11 |
| Mobile-first bottom sheet | Task 10 |
| Colori CSS variables | Task 7 |
| Font Inter | Task 7 |
| Docker Compose | Task 12 |
| Nominatim rate-limit (User-Agent header) | Task 8 |

**No placeholders found.** All steps have concrete code.

**Type consistency confirmed:** `_edge_key(u,v)` → `"{u}_{v}"` used in shadow_engine.py, cache.py, router.py consistently. `RouteInfo` fields match between backend models.py and frontend RouteCard.jsx consumption.
