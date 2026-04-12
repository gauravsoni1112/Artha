"""
LLM configuration loaded from environment / .env file.

Supported providers:
  - anthropic   → uses ANTHROPIC_API_KEY, model default: claude-haiku-4-5-20251001
  - openai      → uses OPENAI_API_KEY, model default: gpt-4o-mini
  - ollama      → uses LLM_BASE_URL (default http://localhost:11434), no key needed

Set in .env (or environment):
  LLM_PROVIDER=anthropic          # anthropic | openai | ollama
  LLM_MODEL=claude-haiku-4-5-20251001
  LLM_API_KEY=sk-...              # not needed for ollama
  LLM_BASE_URL=http://localhost:11434  # ollama only
  LLM_TEMPERATURE=0               # deterministic by default
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    api_key: str | None
    base_url: str | None
    temperature: float

    @classmethod
    def from_env(cls) -> "LLMConfig":
        provider = os.getenv("LLM_PROVIDER", "ollama").lower()

        defaults: dict[str, str] = {
            "anthropic": "claude-haiku-4-5-20251001",
            "openai": "gpt-4o-mini",
            "ollama": "llama3.2",
        }

        model = os.getenv("LLM_MODEL", defaults.get(provider, "llama3.2"))
        api_key = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434")
        temperature = float(os.getenv("LLM_TEMPERATURE", "0"))

        return cls(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
        )

    def build_chat_model(self):
        """Return a LangChain-compatible chat model for the configured provider."""
        if self.provider == "anthropic":
            from langchain_anthropic import ChatAnthropic  # type: ignore[import]
            return ChatAnthropic(
                model=self.model,
                api_key=self.api_key,
                temperature=self.temperature,
            )
        elif self.provider == "openai":
            from langchain_openai import ChatOpenAI  # type: ignore[import]
            return ChatOpenAI(
                model=self.model,
                api_key=self.api_key,
                temperature=self.temperature,
            )
        elif self.provider == "ollama":
            from langchain_ollama import ChatOllama  # type: ignore[import]
            return ChatOllama(
                model=self.model,
                base_url=self.base_url,
                temperature=self.temperature,
            )
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: {self.provider!r}. Choose anthropic, openai, or ollama.")
