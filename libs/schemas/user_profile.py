"""
UserProfile — canonical struct injected into every agent request.

Agents NEVER query profile data themselves; the router/orchestrator
populates this from the owner record and injects it at dispatch time.

All monetary fields are in paise (int64). Never float.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class IncomeSource(BaseModel):
    label: str = Field(..., description="e.g. 'Salary - Acme Corp'")
    monthly_paise: int = Field(..., ge=0)
    is_variable: bool = False


class EMI(BaseModel):
    label: str = Field(..., description="e.g. 'Home Loan - SBI'")
    monthly_paise: int = Field(..., ge=0)
    remaining_months: int = Field(..., ge=0)


class FinancialGoal(BaseModel):
    goal_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    label: str
    target_paise: int = Field(..., ge=0)
    current_paise: int = Field(..., ge=0)
    target_date: date


class UserProfile(BaseModel):
    """
    Canonical user profile. Injected into every AgentRequest.
    Agents are read-only consumers — they must not mutate or persist this.
    """

    owner_id: uuid.UUID
    name: str

    # Income
    income_sources: list[IncomeSource] = Field(default_factory=list)

    # Derived monthly income (paise) — pre-computed by router, not by agents
    total_monthly_income_paise: int = Field(0, ge=0)

    # Liabilities
    emis: list[EMI] = Field(default_factory=list)

    # Goals
    goals: list[FinancialGoal] = Field(default_factory=list)

    # Risk preference: conservative | moderate | aggressive
    risk_appetite: str = "moderate"

    # Family scope — True if query concerns family finances, not just individual
    is_family_scope: bool = False

    # Age (used by risk and tax agents for retirement horizon)
    age: int | None = Field(None, ge=0, le=120)

    @field_validator("risk_appetite")
    @classmethod
    def validate_risk_appetite(cls, v: str) -> str:
        allowed = {"conservative", "moderate", "aggressive"}
        if v not in allowed:
            raise ValueError(f"risk_appetite must be one of {allowed}")
        return v

    @property
    def total_monthly_emi_paise(self) -> int:
        return sum(e.monthly_paise for e in self.emis)

    @property
    def debt_to_income_ratio(self) -> float | None:
        if self.total_monthly_income_paise == 0:
            return None
        return self.total_monthly_emi_paise / self.total_monthly_income_paise
