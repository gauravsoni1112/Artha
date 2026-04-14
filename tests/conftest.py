"""
pytest configuration.

Marks:
  @pytest.mark.integration  — requires Docker + running Postgres
"""

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (require Docker + DB)"
    )


@pytest.fixture
def anyio_backend():
    """Configure asyncio for async tests."""
    return "asyncio"


@pytest.fixture
async def async_client():
    """HTTP test client for the FastAPI app."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
