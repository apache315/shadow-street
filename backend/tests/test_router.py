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


@pytest.fixture
def parallel_edge_graph():
    """A -> B with two parallel edges between the same node pair:

    - edge key 0: 100.0 m, unshaded (shade=0.0) — the "direct sunny" edge.
    - edge key 1: 30.0 m, heavily shaded (shade=0.9) — the "short shaded" edge.

    Both edges connect the exact same (u, v) = (1, 2), so they share the
    same shadow_weights entry "1_2" (edge key is purely topological, not
    keyed by the parallel-edge index). This means the *only* way the
    shadiest-route cost function can distinguish between them is via the
    "length" attribute on each parallel edge's own dict — which is exactly
    what was broken pre-fix: a callable weight on a MultiDiGraph receives
    the multi-edge container {0: {...}, 1: {...}}, so naive `data.get(
    "length", 1.0)` always fell through to the 1.0 default regardless of
    which parallel edge was geometrically being traversed.
    """
    G = nx.MultiDiGraph()
    G.add_node(1, x=10.4000, y=43.7228)
    G.add_node(2, x=10.4020, y=43.7228)
    # Parallel edge 0: long, unshaded.
    G.add_edge(
        1, 2, length=100.0, shade_hint="sunny",
        geometry=LineString([(10.4000, 43.7228), (10.4020, 43.7228)]),
    )
    # Parallel edge 1: short, heavily shaded.
    G.add_edge(
        1, 2, length=30.0, shade_hint="shaded",
        geometry=LineString([(10.4000, 43.7228), (10.4020, 43.7228)]),
    )
    # Return edge for completeness (not exercised by the assertions below).
    G.add_edge(2, 1, length=100.0,
               geometry=LineString([(10.4020, 43.7228), (10.4000, 43.7228)]))
    return G


def test_shadiest_weight_uses_real_edge_length_on_multigraph(parallel_edge_graph):
    """Regression test for C1.

    shadow_weights only has one entry for the topological edge "1_2" (both
    parallel edges share it), so shade alone cannot make the two parallel
    edges differ in the broken implementation (which collapses every edge's
    distance to a hardcoded 1.0). The real annotated route distance must
    come from `_annotate_route`'s min-length edge resolution — and
    crucially, find_routes always returns the geometry/length of *a*
    min-length edge between (u, v) regardless of which one Dijkstra
    "intended": _annotate_route independently re-resolves to the min-length
    parallel edge (30.0 m here) for every consecutive (u, v) pair on the
    path. So total_distance_m for any A->B route on this graph must equal
    30.0 (the shorter of the two parallel edges), not the broken function's
    implicit 1.0-per-edge hop count, and not 100.0 either.
    """
    shadow_weights = {"1_2": 0.9, "2_1": 0.0}

    fastest, shadiest, _ = find_routes(
        parallel_edge_graph,
        start=(43.7228, 10.4000),
        end=(43.7228, 10.4020),
        shadow_weights=shadow_weights,
    )

    # _annotate_route always resolves to the min-length parallel edge (30.0 m)
    # for the (1, 2) hop, independent of which parallel edge Dijkstra's
    # internal bookkeeping associated with the chosen path. This is the
    # "real" distance ground truth, computed from the test's known graph
    # data (not from the function under test).
    expected_real_distance = 30.0

    assert shadiest["total_distance_m"] == pytest.approx(expected_real_distance, rel=0.01)
    assert fastest["total_distance_m"] == pytest.approx(expected_real_distance, rel=0.01)

    # With the bug, _weight_shadiest would have computed a cost of
    # 1.0 + alpha*(1-shade) instead of dist + alpha*dist*(1-shade), i.e. it
    # would never have scaled by the real 30.0 m / 100.0 m edge length at
    # all. Assert the fixed function's cost actually scales with length by
    # calling it directly with the true multi-edge dict shape networkx
    # passes for a MultiDiGraph callable weight.
    from router import _weight_shadiest

    multi_edge_dict = dict(parallel_edge_graph[1][2])
    cost = _weight_shadiest(1, 2, multi_edge_dict, shadow_weights, alpha=2.0)
    # Correct: resolves to the 30.0 m edge -> 30.0 + 2.0 * 30.0 * (1 - 0.9) = 36.0
    assert cost == pytest.approx(36.0, rel=0.01)
    # The pre-fix bug would have produced 1.0 + 2.0 * 1.0 * (1 - 0.9) = 1.2
    assert cost != pytest.approx(1.2, rel=0.01)
