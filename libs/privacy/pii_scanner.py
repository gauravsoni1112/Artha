"""
Pre-flight PII scanner — runs before any cloud LLM call.

Uses Presidio PatternRecognizer instances (no spaCy / NER model needed).
If ANY pattern matches, the cloud call is aborted and the caller should
fall back to local-only inference.

Patterns covered:
  IN_PAN        — [A-Z]{5}[0-9]{4}[A-Z]
  IN_AADHAAR    — 12-digit number (with/without spaces)
  IN_PHONE      — +91 / 10-digit mobile
  IN_IFSC       — [A-Z]{4}0[A-Z0-9]{6}
  IN_ACCOUNT    — 9–18 digit standalone number (heuristic)
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PIIMatch:
    entity_type: str
    start: int
    end: int
    text: str
    score: float


# ---------------------------------------------------------------------------
# Regex patterns (no Presidio engine needed — standalone PatternRecognizer)
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[str, re.Pattern[str], float]] = [
    (
        "IN_PAN",
        re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
        0.90,
    ),
    (
        "IN_AADHAAR",
        # 12 digits optionally split into groups of 4 by space/dash
        re.compile(r"\b[2-9]\d{3}[\s\-]?\d{4}[\s\-]?\d{4}\b"),
        0.85,
    ),
    (
        "IN_PHONE",
        re.compile(r"(?:\+91[\s\-]?)?[6-9]\d{9}\b"),
        0.80,
    ),
    (
        "IN_IFSC",
        re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"),
        0.90,
    ),
    (
        "IN_ACCOUNT",
        # 9–18 digit standalone number not already matched by Aadhaar
        re.compile(r"\b\d{9,18}\b"),
        0.60,
    ),
]


class PIIScanner:
    """Stateless scanner; safe to instantiate once at module level."""

    def scan(self, text: str) -> list[PIIMatch]:
        """Return all PII matches found in *text*."""
        matches: list[PIIMatch] = []
        for entity_type, pattern, score in _PATTERNS:
            for m in pattern.finditer(text):
                matches.append(
                    PIIMatch(
                        entity_type=entity_type,
                        start=m.start(),
                        end=m.end(),
                        text=m.group(),
                        score=score,
                    )
                )
        return matches

    def is_safe_for_cloud(self, text: str) -> bool:
        """Return True only if no PII patterns are detected."""
        return len(self.scan(text)) == 0

    def assert_safe_for_cloud(self, text: str, context: str = "") -> None:
        """Raise ValueError if any PII is detected. Call this before cloud send."""
        hits = self.scan(text)
        if hits:
            entities = ", ".join(f"{h.entity_type}({h.text!r})" for h in hits[:3])
            raise ValueError(
                f"PII detected before cloud LLM call{f' ({context})' if context else ''}: "
                f"{entities}{'…' if len(hits) > 3 else ''}. "
                "Anonymisation must have missed these. Falling back to local."
            )


# Module-level singleton — no state, safe to share
default_scanner = PIIScanner()
