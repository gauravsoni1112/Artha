"""
Anonymiser — scrubs PII from LLM-visible messages before cloud calls.

Works at two layers:
  1. scrub_profile_context() — removes PII injected via the [User profile] header
     (owner_id, raw income paise, name from system prompt).
  2. scrub_messages()        — processes a full LangChain message list, replacing
     any residual PII strings with tokens or category placeholders.

Detokenisation reverses name/merchant tokens in the final answer text so
the user sees real names, not user_a1b2.

PII field rules (mirrors the design spec):
  owner_id (UUID)            → tokenise_name (user_{hex6})
  name                       → tokenise_name
  counterparty / merchant    → merchant_to_category (if known) else tokenise_merchant
  description / narration    → dropped (replaced with "[redacted]")
  amount_paise               → kept as-is
  income_paise               → rounded to nearest ₹5 000 bucket (×100 paise)
  account_number / PAN /
  Aadhaar / IFSC             → replaced by category placeholder via PIIScanner
  dates                      → day-precision kept (cloud only sees aggregates anyway)
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage

from libs.privacy.merchant_map import MERCHANT_CATEGORY_VALUES, merchant_to_category
from libs.privacy.pii_scanner import _PATTERNS
from libs.privacy.token_map import TokenMap

# Bucket income to nearest ₹5 000 (= 500 000 paise)
_INCOME_BUCKET_PAISE = 500_000


def _bucket_income(paise: int) -> int:
    return round(paise / _INCOME_BUCKET_PAISE) * _INCOME_BUCKET_PAISE


def _redact_pattern_matches(text: str) -> str:
    """Replace hard-pattern PII (PAN, Aadhaar, IFSC, account, phone) with placeholders."""
    redactions = {
        "IN_PAN": "[pan_redacted]",
        "IN_AADHAAR": "[aadhaar_redacted]",
        "IN_IFSC": "[ifsc_redacted]",
        "IN_PHONE": "[phone_redacted]",
        "IN_ACCOUNT": "[acct_redacted]",
    }
    for entity_type, pattern, _ in _PATTERNS:
        placeholder = redactions.get(entity_type, "[redacted]")
        text = pattern.sub(placeholder, text)
    return text


class Anonymiser:
    """
    Stateless anonymiser — takes a TokenMap per-request so tokens are
    request-scoped and never shared across requests.
    """

    # ------------------------------------------------------------------ #
    # Profile context scrubbing
    # ------------------------------------------------------------------ #

    def scrub_profile_context(self, content: str, tm: TokenMap) -> str:
        """
        Scrub the [User profile] injected HumanMessage:
          owner_id=<uuid>  → owner_id=<token>
          income=<paise>p  → income=<bucketed>p
        """
        # Replace owner_id UUID
        content = re.sub(
            r"owner_id=([0-9a-f\-]{36})",
            lambda m: f"owner_id={tm.tokenise_name(m.group(1))}",
            content,
        )
        # Bucket income
        content = re.sub(
            r"income=(\d+)p",
            lambda m: f"income={_bucket_income(int(m.group(1)))}p",
            content,
        )
        return content

    def scrub_system_prompt(self, content: str, tm: TokenMap) -> str:
        """Replace the user's real name in the system prompt."""
        # Pattern: "You are Artha, a personal finance assistant for <Name>."
        content = re.sub(
            r"(personal finance assistant for )([^.]+)\.",
            lambda m: f"{m.group(1)}{tm.tokenise_name(m.group(2).strip())}.",
            content,
        )
        return content

    def scrub_tool_result_json(self, json_str: str, tm: TokenMap) -> str:
        """
        Scrub a JSON string from a ToolMessage.
        Applies:
          - Pattern redaction (PAN, Aadhaar, IFSC, phone, account)
          - Merchant name → category
          - Description fields → [redacted]
          - Name fields → token
        """
        try:
            data: dict[str, Any] = json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            # Not JSON — apply text-level scrubbing
            return _redact_pattern_matches(json_str)

        data = self._scrub_dict(data, tm)
        # Apply pattern redaction on the serialised output so integer paise values
        # that passed through _scrub_dict (integers are not pattern-scrubbed inline)
        # get caught before any cloud PII scan.
        return _redact_pattern_matches(json.dumps(data))

    def _scrub_dict(self, data: dict[str, Any], tm: TokenMap) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in data.items():
            key_lower = key.lower()
            if key_lower in {"description", "narration", "remarks", "note", "notes"}:
                out[key] = "[redacted]"
            elif key_lower in {"counterparty_name", "merchant", "payee", "payer"}:
                if isinstance(value, str) and value:
                    if value in tm.reverse or value in MERCHANT_CATEGORY_VALUES:
                        out[key] = value  # already a token or category — idempotent
                    else:
                        cat = merchant_to_category(value)
                        out[key] = cat if cat != "merchant_other" else tm.tokenise_merchant(value)
                else:
                    out[key] = value
            elif key_lower in {"name", "owner_name", "account_holder"}:
                out[key] = tm.tokenise_name(value) if isinstance(value, str) else value
            elif key_lower in {"pan", "aadhaar", "ifsc", "account_number", "account_no"}:
                out[key] = f"[{key_lower}_redacted]"
            elif key_lower in {"total_monthly_income_paise", "income_paise", "monthly_income"}:
                out[key] = _bucket_income(int(value)) if isinstance(value, (int, float)) else value
            elif isinstance(value, str):
                out[key] = _redact_pattern_matches(value)
            elif isinstance(value, dict):
                out[key] = self._scrub_dict(value, tm)
            elif isinstance(value, list):
                out[key] = [
                    self._scrub_dict(v, tm) if isinstance(v, dict)
                    else (_redact_pattern_matches(v) if isinstance(v, str) else v)
                    for v in value
                ]
            else:
                out[key] = value
        return out

    # ------------------------------------------------------------------ #
    # Full message-list scrubbing
    # ------------------------------------------------------------------ #

    def scrub_messages(self, messages: list[BaseMessage], tm: TokenMap) -> list[BaseMessage]:
        """
        Return a new list with PII scrubbed from all messages.
        Only touches SystemMessage, HumanMessage, and ToolMessage (str content).
        AIMessage tool_calls are left unchanged (contain no PII).
        """
        scrubbed: list[BaseMessage] = []
        for msg in messages:
            content = msg.content
            if not isinstance(content, str):
                scrubbed.append(msg)
                continue

            if isinstance(msg, SystemMessage):
                content = self.scrub_system_prompt(content, tm)
            elif isinstance(msg, HumanMessage):
                if content.startswith("[User profile]"):
                    # Chain: structured field scrub then hard-pattern redaction
                    content = self.scrub_profile_context(content, tm)
                    content = _redact_pattern_matches(content)
                else:
                    content = _redact_pattern_matches(content)
            else:
                # ToolMessage or other — try JSON scrub, fall back to text
                content = self.scrub_tool_result_json(content, tm)

            # Reconstruct message preserving required fields (ToolMessage needs tool_call_id)
            if isinstance(msg, ToolMessage):
                scrubbed.append(ToolMessage(content=content, tool_call_id=msg.tool_call_id))
            else:
                scrubbed.append(msg.__class__(content=content))
        return scrubbed

    # ------------------------------------------------------------------ #
    # Detokenisation
    # ------------------------------------------------------------------ #

    def detokenise_answer(self, text: str, tm: TokenMap) -> str:
        """Restore real names/merchants in the final answer before returning to user."""
        return tm.detokenise_regex(text)


# Module-level singleton
default_anonymiser = Anonymiser()
