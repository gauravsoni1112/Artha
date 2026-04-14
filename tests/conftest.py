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


@pytest.fixture
def sample_bank_pdf_bytes() -> bytes:
    """Minimal but valid PDF bytes for testing PDF extraction."""
    # Minimal valid PDF structure with required objects
    return b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj
4 0 obj<</Length 44>>stream
BT /F1 12 Tf 100 700 Td (Mock Bank Statement) Tj ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000203 00000 n
trailer<</Size 5/Root 1 0 R>>
startxref
296
%%EOF"""
