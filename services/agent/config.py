"""
LLM configuration loaded from environment / .env file.

Supported providers:
  - anthropic   → uses LLM_API_KEY (or ANTHROPIC_API_KEY)
  - openai      → uses LLM_API_KEY (or OPENAI_API_KEY)
  - ollama      → uses LLM_BASE_URL, no key needed

Required in .env:
  LLM_PROVIDER=ollama             # anthropic | openai | ollama
  LLM_MODEL=<model-name>          # no default — must be set explicitly
  LLM_API_KEY=                    # not needed for ollama
  LLM_BASE_URL=http://localhost:11434
  LLM_TEMPERATURE=0

Per-role routing (RoutingPolicy):
  {ROLE}_DESTINATION=local|cloud
  {ROLE}_PROVIDER=ollama|anthropic|openai
  {ROLE}_MODEL=<model-name>       # falls back to LLM_MODEL if unset
  {ROLE}_ANONYMISE=false          # must be true when destination=cloud
  Roles: EXECUTOR, COMPACTOR, REFLECTOR, SYNTHESIZER, CRITIC
  See .env.example for full list.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from dotenv import load_dotenv

load_dotenv()


class LLMRole(str, Enum):
    EXECUTOR = "executor"
    COMPACTOR = "compactor"
    REFLECTOR = "reflector"
    SYNTHESIZER = "synthesizer"
    CRITIC = "critic"


# These roles touch raw PII (tool results, pre-anonymisation context) and must
# never be routed to a cloud LLM regardless of anonymise flag.
_LOCAL_ONLY_ROLES: frozenset[LLMRole] = frozenset({LLMRole.EXECUTOR, LLMRole.COMPACTOR})


@dataclass(frozen=True)
class RoutingPolicy:
    """Declarative per-role LLM routing.

    Hard invariants (enforced in __post_init__):
      1. EXECUTOR and COMPACTOR must always be local — they see raw PII before
         anonymisation.
      2. Any cloud destination requires anonymise=True.
    """

    role: LLMRole
    destination: Literal["local", "cloud"]
    provider: str
    model: str
    anonymise: bool = False

    def __post_init__(self) -> None:
        if self.role in _LOCAL_ONLY_ROLES and self.destination == "cloud":
            raise ValueError(
                f"RoutingPolicy for role={self.role!r}: this role processes raw PII "
                "(tool results and pre-anonymisation context) and must always run "
                "locally. Cloud destination is a hard NO for this role."
            )
        if self.destination == "cloud" and not self.anonymise:
            raise ValueError(
                f"RoutingPolicy for role={self.role!r}: cloud destination requires anonymise=True. "
                "Never send PII to a cloud LLM."
            )

    @classmethod
    def from_env(cls, role: LLMRole) -> "RoutingPolicy":
        prefix = role.value.upper()
        destination: Literal["local", "cloud"] = (
            os.getenv(f"{prefix}_DESTINATION", "local").lower()  # type: ignore[assignment]
        )
        provider = (os.getenv(f"{prefix}_PROVIDER") or os.getenv("LLM_PROVIDER", "ollama")).lower()
        model = os.getenv(f"{prefix}_MODEL") or os.getenv("LLM_MODEL")
        if not model:
            raise ValueError(
                f"No model configured for role={role.value!r}. "
                f"Set {prefix}_MODEL or LLM_MODEL in your .env."
            )
        anonymise = os.getenv(f"{prefix}_ANONYMISE", "false").lower() == "true"
        return cls(role=role, destination=destination, provider=provider, model=model, anonymise=anonymise)

    def build_chat_model(self):
        """Build a LangChain chat model from this policy, reading api_key/base_url from env."""
        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        ) or None  # collapse empty strings to None
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434")
        temperature = float(os.getenv("LLM_TEMPERATURE", "0"))
        cfg = LLMConfig(
            provider=self.provider,
            model=self.model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
        )
        return cfg.build_chat_model()


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

        model = os.getenv("LLM_MODEL")
        if not model:
            raise ValueError("LLM_MODEL is not set. Add it to your .env file.")
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
            key = self.api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("LLM_API_KEY")
            if not key:
                raise ValueError(
                    "Anthropic provider requires an API key. "
                    "Set ANTHROPIC_API_KEY or LLM_API_KEY in your .env."
                )
            return ChatAnthropic(model=self.model, api_key=key, temperature=self.temperature)
        elif self.provider == "openai":
            from langchain_openai import ChatOpenAI  # type: ignore[import]
            key = self.api_key or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
            if not key:
                raise ValueError(
                    "OpenAI provider requires an API key. "
                    "Set OPENAI_API_KEY or LLM_API_KEY in your .env."
                )
            return ChatOpenAI(model=self.model, api_key=key, temperature=self.temperature)
        elif self.provider == "ollama":
            from langchain_ollama import ChatOllama  # type: ignore[import]
            return ChatOllama(
                model=self.model,
                base_url=self.base_url,
                temperature=self.temperature,
            )
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: {self.provider!r}. Choose anthropic, openai, or ollama.")
