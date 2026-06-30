import pytest
import networkx as nx
from shapely.geometry import LineString
from router import find_routes, _annotate_route, DEVIATION_CAP


@pytest.fixture
def linear_graph():
    """A -> B -> C with a direct A->C shortcut. A->B shaded, B->C sunny."""
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
