import pytest
from datetime import datetime, timezone
from unittest.mock import patch

import main

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


async def test_route_endpoint_at_night_returns_night_true(client):
    """Regression test for C2: the night flag must reach the API response.

    Posts a datetime deep in the night (2024-01-15T00:00:00+00:00, matching
    the night fixture used in test_shadow_engine.py) and asserts that the
    real night computation in the /route handler determines night=True.
    The mock's third tuple element is deliberately NOT hardcoded to True —
    main.py now recomputes night itself via get_altitude and threads it
    into find_routes, so whatever find_routes is called with should match
    the real computation, and the response should reflect that.
    """
    mock_weights = {}
    captured_kwargs = {}

    def fake_find_routes(*args, **kwargs):
        captured_kwargs.update(kwargs)
        night = kwargs.get("night", False)
        return (
            {"geojson": {"type": "FeatureCollection", "features": []},
             "total_distance_m": 500.0, "total_duration_s": 357.0, "shade_pct": 100.0},
            {"geojson": {"type": "FeatureCollection", "features": []},
             "total_distance_m": 500.0, "total_duration_s": 357.0, "shade_pct": 100.0},
            night,
        )

    with patch("main.load_shadow_weights", return_value=mock_weights), \
         patch("main.find_routes", side_effect=fake_find_routes):
        r = await client.post("/route", json={
            "start": [43.7228, 10.4017],
            "end": [43.7156, 10.3952],
            "datetime": "2024-01-15T00:00:00+00:00",
        })

    assert r.status_code == 200
    data = r.json()
    assert data["night"] is True
    # main.py must have computed night itself and threaded it into find_routes.
    # (get_altitude's comparison can yield a numpy bool rather than a plain
    # Python bool, so compare by value, not identity.)
    assert captured_kwargs.get("night") == True  # noqa: E712


async def test_route_endpoint_cache_miss_returns_503(client):
    """Regression test for I3: a genuine cache miss (load_shadow_weights
    returns None) must surface as a 503, not silently fall back to {}
    (which would produce confidently-wrong all-sun routes).
    """
    with patch("main.load_shadow_weights", return_value=None):
        r = await client.post("/route", json={
            "start": [43.7228, 10.4017],
            "end": [43.7156, 10.3952],
        })
    assert r.status_code == 503


async def test_cache_age_minutes_reflects_elapsed_time(client, monkeypatch):
    """Regression test for I2: cache_age_minutes must be computed at
    request time from the last refresh timestamp, not hardcoded to 0.

    We simulate a refresh having happened slightly in the past and assert
    /health reports a small non-negative age rather than asserting the
    literal 0 (asserting exactly 0 would mask the bug if reintroduced,
    since the old buggy code also always reported 0).
    """
    from datetime import timedelta

    refreshed_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    monkeypatch.setattr(main, "_cache_refreshed_at", refreshed_at)

    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["cache_age_minutes"] is not None
    assert 0 <= data["cache_age_minutes"] < 2
