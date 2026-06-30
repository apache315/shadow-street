import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from main import app


@pytest.fixture
async def client():
    # Patch lifespan so tests don't download OSM data
    with patch("main.refresh_shadow_cache", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
