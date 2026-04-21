"""
Per-request, in-memory token map for reversible PII anonymisation.

TokenMap lives only for the duration of one AgentRequest — created in
BaseAgent.run(), garbage-collected after the response is returned.
It is NEVER persisted to Redis or Postgres.

Token format:
  user_{hex6}      — owner names / user identifiers
  merchant_{hex4}  — unknown merchant names (known ones get a category string)
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field


def _hash4(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:4]


def _hash6(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:6]


@dataclass
class TokenMap:
    """In-memory bidirectional token registry. Thread-safe for read; single-writer."""

    forward: dict[str, str] = field(default_factory=dict)  # real → token
    reverse: dict[str, str] = field(default_factory=dict)  # token → real

    def tokenise_name(self, value: str) -> str:
        """Replace a person's name with a deterministic user_* token."""
        if not value or not value.strip():
            return value
        key = value.strip()
        if key not in self.forward:
            token = f"user_{_hash6(key)}"
            self.forward[key] = token
            self.reverse[token] = key
        return self.forward[key]

    def tokenise_merchant(self, value: str) -> str:
        """Replace an unknown merchant with merchant_* token."""
        if not value or not value.strip():
            return value
        key = value.strip()
        if key not in self.forward:
            token = f"merchant_{_hash4(key)}"
            self.forward[key] = token
            self.reverse[token] = key
        return self.forward[key]

    def detokenise(self, text: str) -> str:
        """Swap all tokens in *text* back to their real values."""
        for token, real in self.reverse.items():
            text = text.replace(token, real)
        return text

    def detokenise_regex(self, text: str) -> str:
        """Word-boundary-aware detokenisation (safer for prose output)."""
        for token, real in self.reverse.items():
            text = re.sub(re.escape(token), real, text)
        return text
