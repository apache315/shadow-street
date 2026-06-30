from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional

import networkx as nx
import geopandas as gpd
from shapely.geometry import LineString, Point, MultiPolygon, Polygon
from shapely.ops import transform, unary_union
from shapely.affinity import translate
from shapely.prepared import prep
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


def _edge_key(u: int, v: int) -> str:
    """Return the canonical string key for a directed edge."""
    return f"{u}_{v}"


def _project_building_shadow(
    footprint_utm: Polygon,
    height_m: float,
    sun_alt_deg: float,
    sun_az_deg: float,
) -> Polygon:
    """Project a building footprint into its shadow polygon (UTM coords).

    The shadow is cast in the direction opposite the sun azimuth.
    Returns the union of the footprint and the translated shadow so the
    result always covers at least the building footprint area.
    """
    shadow_length = height_m / math.tan(math.radians(sun_alt_deg))
    # Shadow direction is opposite to sun azimuth
    shadow_az = (sun_az_deg + 180) % 360
    dx = shadow_length * math.sin(math.radians(shadow_az))
    dy = shadow_length * math.cos(math.radians(shadow_az))
    shadow = translate(footprint_utm, xoff=dx, yoff=dy)
    return footprint_utm.union(shadow)


def _edge_shade_fraction(
    geom_wgs84: LineString,
    shadow_union: Optional[Any],
    tree_union: Optional[Any],
) -> float:
    """Sample points along an edge and compute the weighted shade fraction.

    Building shadow counts as full shade (weight 1.0).
    Tree canopy counts as partial shade (weight TREE_SHADE_FRACTION).
    """
    geom_utm = transform(_to_utm.transform, geom_wgs84)
    length = geom_utm.length
    n = max(2, int(length / SAMPLE_STEP_M))
    points = [geom_utm.interpolate(i / (n - 1), normalized=True) for i in range(n)]

    building_hits = sum(
        1 for p in points
        if shadow_union is not None and shadow_union.contains(p)
    )
    tree_hits = sum(
        1 for p in points
        if (shadow_union is None or not shadow_union.contains(p))
        and tree_union is not None and tree_union.contains(p)
    )

    shade = (building_hits + tree_hits * TREE_SHADE_FRACTION) / len(points)
    return min(1.0, shade)


def compute_shadow_weights(
    dt: datetime,
    G: nx.MultiDiGraph,
    buildings: gpd.GeoDataFrame,
    trees: gpd.GeoDataFrame,
    covered_edges: set,
) -> tuple[dict[str, float], bool]:
    """Compute per-edge shade fractions for a given datetime.

    Parameters
    ----------
    dt:
        The moment to compute shadows for (UTC recommended).
    G:
        OSM pedestrian graph from load_walk_graph().
    buildings:
        GeoDataFrame with columns 'geometry' (WGS84 polygons) and 'height_m'.
    trees:
        GeoDataFrame with column 'geometry' (WGS84 points or polygons).
    covered_edges:
        Set of (u, v) tuples that are permanently shaded (covered walkways,
        tunnels, etc.).

    Returns
    -------
    weights : dict[str, float]
        Mapping from edge key "{u}_{v}" to shade fraction in [0.0, 1.0].
    night : bool
        True when the sun is below the horizon (shade fraction forced to 1.0).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    sun_alt = get_altitude(PISA_LAT, PISA_LON, dt)
    sun_az = get_azimuth(PISA_LAT, PISA_LON, dt)

    # Night: sun below the horizon — full shade everywhere
    if sun_alt <= 0:
        weights = {_edge_key(u, v): 1.0 for u, v, _ in G.edges(data=True)}
        return weights, True

    # Twilight: sun too low for reliable shadow geometry — high shade
    if sun_alt < TWILIGHT_ALTITUDE:
        weights = {_edge_key(u, v): 0.8 for u, v, _ in G.edges(data=True)}
        for u, v in covered_edges:
            weights[_edge_key(u, v)] = 1.0
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
    if shadow_union is not None:
        shadow_union = prep(shadow_union)

    # Build tree canopy union (fixed circles — sun direction agnostic for MVP)
    tree_polys = []
    for _, row in trees.iterrows():
        try:
            geom_utm = transform(_to_utm.transform, row.geometry)
            tree_polys.append(geom_utm.buffer(TREE_CANOPY_RADIUS_M))
        except Exception:
            continue
    tree_union = unary_union(tree_polys) if tree_polys else None
    if tree_union is not None:
        tree_union = prep(tree_union)

    weights: dict = {}
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
