from __future__ import annotations

import pickle
from pathlib import Path
from typing import Optional, Set, Tuple

import networkx as nx

try:
    import geopandas as gpd
    import osmnx as ox
    _HAS_OSM = True
except ImportError:
    _HAS_OSM = False

PISA_PLACE = "Pisa, Italy"
CACHE_DIR = Path("data/osm_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _parse_height(row: dict) -> float:
    """Parse a building height from an OSM tag dict.

    Checks 'building:levels' first (multiplied by 3 m/floor),
    then 'height' (strips trailing 'm'), then falls back to 9.0 m.
    """
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
    """Return the OSM pedestrian graph for Pisa.

    Uses a pickle cache in CACHE_DIR.  Downloads via osmnx on first call.
    """
    cache_path = CACHE_DIR / "walk_graph.pkl"
    if cache_path.exists():
        with open(cache_path, "rb") as f:
            return pickle.load(f)
    if not _HAS_OSM:
        raise ImportError(
            "osmnx is not installed; cannot download walk graph. "
            "Install osmnx or provide a cached walk_graph.pkl."
        )
    G = ox.graph_from_place(PISA_PLACE, network_type="walk")
    with open(cache_path, "wb") as f:
        pickle.dump(G, f)
    return G


def load_buildings() -> "gpd.GeoDataFrame":
    """Return a GeoDataFrame of Pisa buildings with columns: geometry, height_m.

    Uses a parquet cache in CACHE_DIR.  Downloads via osmnx on first call.
    """
    cache_path = CACHE_DIR / "buildings.pkl"
    if cache_path.exists():
        return gpd.read_parquet(cache_path)
    if not _HAS_OSM:
        raise ImportError(
            "osmnx/geopandas is not installed; cannot download buildings. "
            "Install osmnx or provide a cached buildings.pkl."
        )
    gdf = ox.features_from_place(PISA_PLACE, tags={"building": True})
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    gdf["height_m"] = gdf.apply(
        lambda row: _parse_height(row.to_dict()), axis=1
    )
    gdf = gdf[["geometry", "height_m"]].reset_index(drop=True)
    gdf.to_parquet(cache_path)
    return gdf


def load_trees() -> "gpd.GeoDataFrame":
    """Return a GeoDataFrame of Pisa trees (geometry column only).

    Uses a parquet cache in CACHE_DIR.  Downloads via osmnx on first call.
    Returns an empty GeoDataFrame if OSM returns no results.
    """
    cache_path = CACHE_DIR / "trees.pkl"
    if cache_path.exists():
        return gpd.read_parquet(cache_path)
    if not _HAS_OSM:
        raise ImportError(
            "osmnx/geopandas is not installed; cannot download trees. "
            "Install osmnx or provide a cached trees.pkl."
        )
    tags = {"natural": ["tree", "tree_row"]}
    try:
        gdf = ox.features_from_place(PISA_PLACE, tags=tags)
    except Exception:
        return gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")
    gdf = gdf[["geometry"]].reset_index(drop=True)
    gdf.to_parquet(cache_path)
    return gdf


def get_covered_edges(G: nx.MultiDiGraph) -> set:
    """Return the set of (u, v) edge tuples that are covered or tunnelled.

    An edge is included if its OSM data has covered='yes' or tunnel='yes'.
    Multi-edges are deduplicated to a single (u, v) pair.
    """
    covered: Set[Tuple[int, int]] = set()
    for u, v, data in G.edges(data=True):
        if data.get("covered") == "yes" or data.get("tunnel") == "yes":
            covered.add((u, v))
    return covered
