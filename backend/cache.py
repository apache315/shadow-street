from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

CACHE_DIR = Path("data/shadow_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
ROME_TZ = ZoneInfo("Europe/Rome")


def cache_slot(dt: datetime) -> str:
    """Return the cache slot string 'HHMM' for the given datetime.

    Floors to the nearest 30-minute boundary using Europe/Rome local time.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(ROME_TZ)
    # Floor to nearest 30-min slot
    minute = 0 if local.minute < 30 else 30
    return f"{local.hour:02d}{minute:02d}"


def save_shadow_weights(weights: dict, dt: datetime) -> None:
    """Persist shadow weights to a JSON file in CACHE_DIR."""
    slot = cache_slot(dt)
    path = CACHE_DIR / f"shadows_{slot}.json"
    path.write_text(json.dumps(weights))


def load_shadow_weights(dt: datetime) -> Optional[dict]:
    """Load shadow weights for the cache slot corresponding to dt.

    Returns None if the file does not exist.
    """
    slot = cache_slot(dt)
    path = CACHE_DIR / f"shadows_{slot}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())
