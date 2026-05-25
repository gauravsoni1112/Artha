"""
Numeric grounding check (Fix 5).

After the reflection loop produces a draft answer, this module verifies that
every ₹ figure cited in the answer can be traced back to a tool output.
If amounts appear that cannot be explained by tool data, the answer is flagged
as potentially hallucinated so the caller can cap confidence and add a warning.

Design decisions:
- Amounts are compared after rounding to the nearest rupee (paise noise is
  irrelevant at the display level).
- The check is one-way: tool amounts that do NOT appear in the answer are fine
  (the LLM may legitimately summarise or omit figures).
- "Close enough" tolerance is ±1 rupee to absorb rounding during formatting.
- Only amounts ≥ ₹1 (≥ 100 paise) are considered; sub-rupee values are noise.
"""

from __future__ import annotations

import re

from services.agent.metrics import record_grounding_check

# ── Amount extraction ──────────────────────────────────────────────────────────

# Matches ₹ amounts in Indian formats:
#   ₹1,00,000   ₹1,00,000.50   ₹50000   ₹50,000.00
_INR_RE = re.compile(
    r"₹\s*([\d,]+(?:\.\d{1,2})?)"
)


def extract_inr_amounts(text: str) -> set[int]:
    """
    Return all ₹ amounts found in *text* as paise integers, rounded to rupee.

    Only amounts ≥ ₹1 (100 paise) are included.
    """
    amounts: set[int] = set()
    for m in _INR_RE.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            rupees = float(raw)
        except ValueError:
            continue
        paise = round(rupees * 100)
        if paise >= 100:
            amounts.add(paise)
    return amounts


# ── Grounding check ────────────────────────────────────────────────────────────

_TOLERANCE_PAISE = 100  # ±₹1


def _amounts_close(a: int, b: int) -> bool:
    return abs(a - b) <= _TOLERANCE_PAISE


def check_answer_grounding(answer: str, tool_outputs: list[str]) -> tuple[bool, list[int]]:
    """
    Check whether ₹ figures in *answer* are supported by *tool_outputs*.

    Args:
        answer:       The LLM's draft answer text.
        tool_outputs: List of raw tool result strings collected during execution.

    Returns:
        (is_grounded, ungrounded_amounts_paise)
        - is_grounded: True if every cited amount can be traced to a tool output.
        - ungrounded_amounts_paise: amounts in paise that could NOT be traced.
    """
    answer_amounts = extract_inr_amounts(answer)
    if not answer_amounts:
        return True, []

    all_tool_text = " ".join(tool_outputs)
    tool_amounts = extract_inr_amounts(all_tool_text)

    ungrounded: list[int] = []
    for amt in answer_amounts:
        if not any(_amounts_close(amt, t) for t in tool_amounts):
            ungrounded.append(amt)

    is_grounded = len(ungrounded) == 0
    record_grounding_check(is_grounded, len(ungrounded))
    return is_grounded, ungrounded
