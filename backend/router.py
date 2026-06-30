from __future__ import annotations

from typing import Optional, Dict, List, Tuple
from shapely.geometry import mapping, LineString
import networkx as nx

try:
    import osmnx as ox
    _HAS_OSMNX = True
except ImportError:
    _HAS_OSMNX = False

DEVIATION_CAP = 1.5
WALKING_SPEED_MS = 1.4


def _edge_key(u: int, v: int) -> str:
    return f"{u}_{v}"


def _nearest_node_fallback(G: nx.MultiDiGraph, lng: float, lat: float) -> int:
    """Pure-networkx nearest-node by Euclidean distance in lon/lat space."""
    best_node = None
    best_dist = float("inf")
    for node, data in G.nodes(data=True):
        dx = data.get("x", 0.0) - lng
        dy = data.get("y", 0.0) - lat
        d = dx * dx + dy * dy
        if d < best_dist:
            best_dist = d
            best_node = node
    return best_node


def _get_nearest_node(G: nx.MultiDiGraph, lng: float, lat: float) -> int:
    if _HAS_OSMNX:
        return ox.distance.nearest_nodes(G, X=lng, Y=lat)
    return _nearest_node_fallback(G, lng, lat)


def _weight_shadiest(
    u: int,
    v: int,
    data: dict,
    shadow_weights: Dict[str, float],
    alpha: float,
) -> float:
    dist = data.get("length", 1.0)
    shade = shadow_weights.get(_edge_key(u, v), 0.0)
    sun_exposed = dist * (1 - shade)
    return dist + alpha * sun_exposed


def _annotate_route(
    G: nx.MultiDiGraph,
    path: List[int],
    shadow_weights: Dict[str, float],
) -> dict:
    """Build a GeoJSON FeatureCollection for a route path.

    Returns a dict with keys: geojson, total_distance_m,
    total_duration_s, shade_pct.
    """
    features = []
    total_dist = 0.0
    total_shade_dist = 0.0

    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        edge_data = min(
            G[u][v].values(),
            key=lambda d: d.get("length", float("inf")),
        )
        geom = edge_data.get(
            "geometry",
            LineString(
                [
                    (G.nodes[u]["x"], G.nodes[u]["y"]),
                    (G.nodes[v]["x"], G.nodes[v]["y"]),
                ]
            ),
        )
        dist = edge_data.get("length", geom.length)
        shade = shadow_weights.get(_edge_key(u, v), 0.0)

        features.append(
            {
                "type": "Feature",
                "geometry": mapping(geom),
                "properties": {
                    "shade_pct": round(shade * 100, 1),
                    "distance_m": round(dist, 1),
                    "duration_s": round(dist / WALKING_SPEED_MS, 1),
                },
            }
        )
        total_dist += dist
        total_shade_dist += dist * shade

    shade_pct = (
        round(total_shade_dist / total_dist * 100, 1) if total_dist > 0 else 0.0
    )
    return {
        "geojson": {"type": "FeatureCollection", "features": features},
        "total_distance_m": round(total_dist, 1),
        "total_duration_s": round(total_dist / WALKING_SPEED_MS, 1),
        "shade_pct": shade_pct,
    }


def find_routes(
    G: nx.MultiDiGraph,
    start: Tuple[float, float],
    end: Tuple[float, float],
    shadow_weights: Dict[str, float],
    alpha: float = 2.0,
) -> Tuple[dict, dict, bool]:
    """Compute fastest and shadiest walking routes on graph G.

    Parameters
    ----------
    G:
        OSMnx-style MultiDiGraph with node attributes ``x`` (lng) and ``y``
        (lat), and edge attribute ``length`` (metres).
    start:
        ``(lat, lng)`` of the origin.
    end:
        ``(lat, lng)`` of the destination.
    shadow_weights:
        Mapping from edge key ``"{u}_{v}"`` to shade fraction in [0, 1].
    alpha:
        Penalty multiplier for sun-exposed distance (default 2.0).

    Returns
    -------
    tuple
        ``(fastest_info, shadiest_info, night_flag)`` where each info dict
        has keys ``geojson``, ``total_distance_m``, ``total_duration_s``,
        and ``shade_pct``.  ``night_flag`` is always ``False`` (determined
        upstream by the shadow engine).
    """
    start_lat, start_lng = start
    end_lat, end_lng = end

    start_node = _get_nearest_node(G, start_lng, start_lat)
    end_node = _get_nearest_node(G, end_lng, end_lat)

    # --- Fastest route (Dijkstra by raw length) ---
    fastest_path = nx.shortest_path(G, start_node, end_node, weight="length")
    fastest_info = _annotate_route(G, fastest_path, shadow_weights)

    # --- Shadiest route (shade-weighted cost) ---
    shadiest_path = nx.shortest_path(
        G,
        start_node,
        end_node,
        weight=lambda u, v, d: _weight_shadiest(u, v, d, shadow_weights, alpha),
    )
    shadiest_info = _annotate_route(G, shadiest_path, shadow_weights)

    # Deviation cap: if shadiest detour exceeds 1.5x fastest, fall back
    if (
        shadiest_info["total_distance_m"]
        > DEVIATION_CAP * fastest_info["total_distance_m"]
    ):
        shadiest_info = fastest_info.copy()

    return fastest_info, shadiest_info, False
