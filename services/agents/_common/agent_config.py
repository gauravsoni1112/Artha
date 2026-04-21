"""
Per-agent LLM configuration.

Shared Ollama instance by default. Each agent can override via its own
env vars:

  <AGENT_ID_UPPER>_LLM_PROVIDER   e.g. CASHFLOW_AGENT_LLM_PROVIDER=anthropic
  <AGENT_ID_UPPER>_LLM_MODEL      e.g. CASHFLOW_AGENT_LLM_MODEL=claude-haiku-4-5-20251001
  <AGENT_ID_UPPER>_LLM_BASE_URL   e.g. CASHFLOW_AGENT_LLM_BASE_URL=http://ollama2:11434

Falls back to global LLM_PROVIDER / LLM_MODEL / LLM_BASE_URL if the
per-agent var is absent.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from services.agent.config import LLMConfig

load_dotenv()


def agent_llm_config(agent_id: str) -> LLMConfig:
    """
    Build an LLMConfig for *agent_id*, honouring per-agent env overrides.

    Example — for agent_id="cashflow_agent":
      CASHFLOW_AGENT_LLM_PROVIDER overrides LLM_PROVIDER
      CASHFLOW_AGENT_LLM_MODEL    overrides LLM_MODEL
      CASHFLOW_AGENT_LLM_BASE_URL overrides LLM_BASE_URL
    """
    prefix = agent_id.upper().replace("-", "_") + "_LLM_"

    def _get(key: str, fallback_key: str, default: str) -> str:
        return (
            os.getenv(f"{prefix}{key}")
            or os.getenv(fallback_key, default)
        )

    provider = _get("PROVIDER", "LLM_PROVIDER", "ollama").lower()

    model = os.getenv(f"{prefix}MODEL") or os.getenv("LLM_MODEL")
    if not model:
        raise ValueError(
            f"No model configured for agent {agent_id!r}. "
            f"Set {prefix}MODEL or LLM_MODEL in your .env."
        )
    base_url = _get("BASE_URL", "LLM_BASE_URL", "http://localhost:11434")
    temperature = float(
        os.getenv(f"{prefix}TEMPERATURE")
        or os.getenv("LLM_TEMPERATURE", "0")
    )
    api_key = (
        os.getenv(f"{prefix}API_KEY")
        or os.getenv("LLM_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )

    return LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
    )
