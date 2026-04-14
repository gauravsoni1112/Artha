"""Tests for per-agent LLM config with env overrides."""

import pytest
from unittest.mock import patch


def test_defaults_to_global_llm_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "llama3.2")
    monkeypatch.setenv("LLM_BASE_URL", "http://ollama:11434")

    from services.agents._common.agent_config import agent_llm_config
    cfg = agent_llm_config("cashflow_agent")

    assert cfg.provider == "ollama"
    assert cfg.model == "llama3.2"
    assert cfg.base_url == "http://ollama:11434"


def test_per_agent_provider_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("CASHFLOW_AGENT_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("CASHFLOW_AGENT_LLM_MODEL", "claude-haiku-4-5-20251001")
    monkeypatch.setenv("CASHFLOW_AGENT_LLM_API_KEY", "sk-test")

    from services.agents._common.agent_config import agent_llm_config
    cfg = agent_llm_config("cashflow_agent")

    assert cfg.provider == "anthropic"
    assert cfg.model == "claude-haiku-4-5-20251001"
    assert cfg.api_key == "sk-test"


def test_per_agent_base_url_override(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://ollama-shared:11434")
    monkeypatch.setenv("TAX_AGENT_LLM_BASE_URL", "http://ollama-tax:11434")

    from services.agents._common.agent_config import agent_llm_config
    cfg_tax = agent_llm_config("tax_agent")
    cfg_other = agent_llm_config("cashflow_agent")

    assert cfg_tax.base_url == "http://ollama-tax:11434"
    assert cfg_other.base_url == "http://ollama-shared:11434"


def test_different_agents_use_different_configs(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("INVESTMENT_AGENT_LLM_PROVIDER", "openai")

    from services.agents._common.agent_config import agent_llm_config
    cashflow_cfg = agent_llm_config("cashflow_agent")
    investment_cfg = agent_llm_config("investment_agent")

    assert cashflow_cfg.provider == "ollama"
    assert investment_cfg.provider == "openai"


def test_temperature_per_agent_override(monkeypatch):
    monkeypatch.setenv("LLM_TEMPERATURE", "0")
    monkeypatch.setenv("RISK_AGENT_LLM_TEMPERATURE", "0.3")

    from services.agents._common.agent_config import agent_llm_config
    cfg = agent_llm_config("risk_agent")

    assert cfg.temperature == pytest.approx(0.3)


def test_hyphenated_agent_id_normalised(monkeypatch):
    """agent-id with hyphens → env prefix uses underscores."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("GOAL_AGENT_LLM_PROVIDER", "anthropic")

    from services.agents._common.agent_config import agent_llm_config
    cfg = agent_llm_config("goal_agent")
    assert cfg.provider == "anthropic"
