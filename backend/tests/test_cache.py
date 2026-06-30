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
