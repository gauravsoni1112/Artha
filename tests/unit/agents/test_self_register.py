"""
Unit tests for self_register — validates env parsing and payload construction.

We don't exercise the HTTP retry loop here (that's integration); we test
that the required-env guard and payload shape are correct.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def test_require_env_raises_when_missing(monkeypatch):
    monkeypatch.delenv("AGENT_ID", raising=False)
    monkeypatch.delenv("AGENT_ENDPOINT", raising=False)
    monkeypatch.delenv("REGISTRY_URL", raising=False)
    monkeypatch.delenv("AGENT_CAPABILITIES", raising=False)

    from services.agents._common.self_register import _require_env
    with pytest.raises(RuntimeError, match="AGENT_ID"):
        _require_env("AGENT_ID")


def test_require_env_returns_value(monkeypatch):
    monkeypatch.setenv("AGENT_ID", "cashflow_agent")

    from services.agents._common.self_register import _require_env
    assert _require_env("AGENT_ID") == "cashflow_agent"


@pytest.mark.asyncio
async def test_self_register_success(monkeypatch):
    monkeypatch.setenv("AGENT_ID", "cashflow_agent")
    monkeypatch.setenv("AGENT_ENDPOINT", "http://cashflow_agent:8001")
    monkeypatch.setenv("REGISTRY_URL", "http://registry:8000")
    monkeypatch.setenv("AGENT_CAPABILITIES", "cashflow,spending,budget")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.put = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        from services.agents._common import self_register as sr_module
        import importlib
        importlib.reload(sr_module)
        await sr_module.self_register()

    call_kwargs = mock_client.put.call_args
    payload = call_kwargs.kwargs["json"]

    assert payload["agent_id"] == "cashflow_agent"
    assert payload["endpoint"] == "http://cashflow_agent:8001"
    assert payload["health_endpoint"] == "http://cashflow_agent:8001/health"
    assert set(payload["capabilities"]) == {"cashflow", "spending", "budget"}
    assert payload["schema_version"] == "1.0"


@pytest.mark.asyncio
async def test_self_register_payload_defaults(monkeypatch):
    monkeypatch.setenv("AGENT_ID", "tax_agent")
    monkeypatch.setenv("AGENT_ENDPOINT", "http://tax_agent:8004")
    monkeypatch.setenv("REGISTRY_URL", "http://api:8000")
    monkeypatch.setenv("AGENT_CAPABILITIES", "tax")
    monkeypatch.delenv("AGENT_TIMEOUT_MS", raising=False)
    monkeypatch.delenv("AGENT_FALLBACK_STRATEGY", raising=False)
    monkeypatch.delenv("AGENT_CACHE_TTL_HOURS", raising=False)
    monkeypatch.delenv("AGENT_SCOPE", raising=False)

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.put = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        from services.agents._common import self_register as sr_module
        import importlib
        importlib.reload(sr_module)
        await sr_module.self_register()

    payload = mock_client.put.call_args.kwargs["json"]
    assert payload["timeout_ms"] == 10000
    assert payload["fallback_strategy"] == "cached_response"
    assert payload["cache_ttl_hours"] == 1.0
    assert payload["scope"] == "individual"
