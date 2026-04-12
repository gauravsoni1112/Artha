"""
Shared ToolResult schema.

Every tool returns a ToolResult so the agent can:
  1. Attach data_freshness to every response.
  2. Serialize uniformly to JSON for the LLM.
  3. Surface metadata (e.g. currency, fiscal_year) alongside raw data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    tool_name: str
    data: dict[str, Any]
    data_freshness: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this result was computed",
    )
    query_params: dict[str, Any] = Field(default_factory=dict)
    currency: str = "INR"
    warnings: list[str] = Field(default_factory=list)

    def to_llm_str(self) -> str:
        """Compact JSON representation sent back to the LLM as a tool observation."""
        import json

        payload = self.model_dump(mode="json")
        # ISO format for datetime
        payload["data_freshness"] = self.data_freshness.isoformat()
        return json.dumps(payload, ensure_ascii=False)
