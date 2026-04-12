"""
pytest configuration.

Marks:
  @pytest.mark.integration  — requires Docker + running Postgres
"""

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (require Docker + DB)"
    )
