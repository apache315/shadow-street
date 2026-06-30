from __future__ import annotations

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


def test_covered_edge_full_shade_during_twilight(tiny_graph, empty_buildings, empty_trees):
    # Low sun angle → twilight, but covered edge must still be 1.0
    dt = datetime(2024, 1, 15, 7, 30, 0, tzinfo=timezone.utc)  # early morning, low sun (5.50°)
    covered = {(1, 2)}
    weights, night = compute_shadow_weights(dt, tiny_graph, empty_buildings, empty_trees, covered)
    assert night is False
    assert weights[_edge_key(1, 2)] == 1.0
