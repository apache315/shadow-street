from __future__ import annotations

import pytest
import networkx as nx
try:
    import geopandas as gpd
    _HAS_GPD = True
except ImportError:
    gpd = None  # type: ignore[assignment]
    _HAS_GPD = False
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
