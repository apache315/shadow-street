import pytest
from unittest.mock import patch

pytestmark = pytest.mark.asyncio


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "cache_age_minutes" in data


async def test_route_endpoint_returns_two_routes(client):
    mock_weights = {}
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
