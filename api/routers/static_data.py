"""
Static data router — typed form endpoints over POST /ingest/MANUAL.

Rather than accepting raw JSON, each endpoint enforces a typed schema for
its asset class, then serialises to the transaction dict format the
ManualConnector expects.

POST /owners/{owner_id}/static-data/insurance    — insurance policy entry
POST /owners/{owner_id}/static-data/real-estate  — real estate asset entry
POST /owners/{owner_id}/static-data/gold         — gold holding entry
POST /owners/{owner_id}/static-data/itr          — ITR / tax summary entry
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_session
from api.dependencies import get_ingestion_service
from api.deps import current_owner
from libs.schemas.db_models import Account, Owner
from libs.schemas.enums import DocumentType, TriggerType
from services.ingestion.connectors.manual_connector import ManualConnector
from sqlalchemy import select

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/owners/{owner_id}/static-data", tags=["static-data"])


# ---------------------------------------------------------------------------
# Common response
# ---------------------------------------------------------------------------


class StaticDataResponse(BaseModel):
    run_id: uuid.UUID
    status: str
    records_passed: int
    records_quarantined: int


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _check_access(requesting_owner: Owner, target_owner_id: uuid.UUID) -> None:
    if not requesting_owner.is_admin and requesting_owner.id != target_owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def _ingest(
    owner_id: uuid.UUID,
    account_id: uuid.UUID,
    doc_type: DocumentType,
    transactions: list[dict[str, Any]],
) -> StaticDataResponse:
    payload_bytes = json.dumps({"transactions": transactions}).encode()
    connector = ManualConnector(payload_bytes=payload_bytes, doc_type=doc_type, account_id=account_id)
    async with get_ingestion_service() as svc:
        documents = await connector.fetch(owner_id)
        result = await svc.run(owner_id, documents[0], trigger_type=TriggerType.ADHOC)
    return StaticDataResponse(
        run_id=result.run_id,
        status=result.status,
        records_passed=result.records_passed,
        records_quarantined=result.records_quarantined,
    )


async def _resolve_account(
    session: AsyncSession, owner_id: uuid.UUID, account_id: uuid.UUID
) -> Account:
    result = await session.execute(
        select(Account).where(Account.id == account_id, Account.owner_id == owner_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found for owner {owner_id}",
        )
    return account


# ---------------------------------------------------------------------------
# Insurance
# ---------------------------------------------------------------------------


class InsuranceEntryRequest(BaseModel):
    account_id: uuid.UUID
    policy_name: str = Field(min_length=1, max_length=256)
    insurer: str = Field(min_length=1, max_length=128)
    policy_type: str = Field(
        description="LIFE | HEALTH | VEHICLE | TERM | ULIP | OTHER",
        pattern="^(LIFE|HEALTH|VEHICLE|TERM|ULIP|OTHER)$",
    )
    sum_assured_paise: int = Field(gt=0)
    annual_premium_paise: int = Field(gt=0)
    policy_start_date: date
    policy_end_date: date | None = None
    nominees: list[str] = Field(default_factory=list)


@router.post("/insurance", response_model=StaticDataResponse, status_code=status.HTTP_201_CREATED)
async def add_insurance(
    owner_id: uuid.UUID,
    body: InsuranceEntryRequest,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> StaticDataResponse:
    _check_access(requesting_owner, owner_id)
    await _resolve_account(session, owner_id, body.account_id)

    transactions = [
        {
            "transaction_date": body.policy_start_date.isoformat(),
            "amount": body.annual_premium_paise,
            "transaction_type": "DEBIT",
            "description": f"Insurance premium — {body.policy_name} ({body.insurer})",
            "category": "INSURANCE",
            "metadata": {
                "policy_name": body.policy_name,
                "insurer": body.insurer,
                "policy_type": body.policy_type,
                "sum_assured_paise": body.sum_assured_paise,
                "policy_end_date": body.policy_end_date.isoformat() if body.policy_end_date else None,
                "nominees": body.nominees,
            },
        }
    ]
    return await _ingest(owner_id, body.account_id, DocumentType.INSURANCE, transactions)


# ---------------------------------------------------------------------------
# Real estate
# ---------------------------------------------------------------------------


class RealEstateEntryRequest(BaseModel):
    account_id: uuid.UUID
    property_name: str = Field(min_length=1, max_length=256)
    property_type: str = Field(pattern="^(RESIDENTIAL|COMMERCIAL|PLOT|OTHER)$")
    purchase_date: date
    purchase_price_paise: int = Field(gt=0)
    current_value_paise: int = Field(gt=0)
    address: str | None = Field(default=None, max_length=512)
    loan_outstanding_paise: int = Field(default=0, ge=0)


@router.post("/real-estate", response_model=StaticDataResponse, status_code=status.HTTP_201_CREATED)
async def add_real_estate(
    owner_id: uuid.UUID,
    body: RealEstateEntryRequest,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> StaticDataResponse:
    _check_access(requesting_owner, owner_id)
    await _resolve_account(session, owner_id, body.account_id)

    transactions = [
        {
            "transaction_date": body.purchase_date.isoformat(),
            "amount": body.purchase_price_paise,
            "transaction_type": "DEBIT",
            "description": f"Real estate purchase — {body.property_name}",
            "category": "INVESTMENT",
            "metadata": {
                "property_type": body.property_type,
                "current_value_paise": body.current_value_paise,
                "address": body.address,
                "loan_outstanding_paise": body.loan_outstanding_paise,
            },
        }
    ]
    return await _ingest(owner_id, body.account_id, DocumentType.OTHER, transactions)


# ---------------------------------------------------------------------------
# Gold
# ---------------------------------------------------------------------------


class GoldEntryRequest(BaseModel):
    account_id: uuid.UUID
    gold_type: str = Field(pattern="^(PHYSICAL|DIGITAL|SOVEREIGN_BOND|ETF|OTHER)$")
    purchase_date: date
    quantity_grams: float = Field(gt=0)
    purchase_price_paise: int = Field(gt=0, description="Total purchase price in paise")
    current_value_paise: int = Field(gt=0)
    description: str | None = Field(default=None, max_length=256)


@router.post("/gold", response_model=StaticDataResponse, status_code=status.HTTP_201_CREATED)
async def add_gold(
    owner_id: uuid.UUID,
    body: GoldEntryRequest,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> StaticDataResponse:
    _check_access(requesting_owner, owner_id)
    await _resolve_account(session, owner_id, body.account_id)

    desc = body.description or f"Gold holding — {body.gold_type} ({body.quantity_grams}g)"
    transactions = [
        {
            "transaction_date": body.purchase_date.isoformat(),
            "amount": body.purchase_price_paise,
            "transaction_type": "DEBIT",
            "description": desc,
            "category": "INVESTMENT",
            "metadata": {
                "gold_type": body.gold_type,
                "quantity_grams": body.quantity_grams,
                "current_value_paise": body.current_value_paise,
            },
        }
    ]
    return await _ingest(owner_id, body.account_id, DocumentType.OTHER, transactions)


# ---------------------------------------------------------------------------
# ITR / Tax summary
# ---------------------------------------------------------------------------


class ITREntryRequest(BaseModel):
    account_id: uuid.UUID
    fiscal_year: str = Field(
        pattern=r"^\d{4}-\d{2}$",
        description="e.g. 2024-25",
    )
    gross_income_paise: int = Field(ge=0)
    taxable_income_paise: int = Field(ge=0)
    tax_paid_paise: int = Field(ge=0)
    tds_paise: int = Field(default=0, ge=0)
    itr_filed: bool = False
    deductions_80c_paise: int = Field(default=0, ge=0)
    deductions_80d_paise: int = Field(default=0, ge=0)


@router.post("/itr", response_model=StaticDataResponse, status_code=status.HTTP_201_CREATED)
async def add_itr(
    owner_id: uuid.UUID,
    body: ITREntryRequest,
    requesting_owner: Annotated[Owner, Depends(current_owner)],
    session: AsyncSession = Depends(get_session),
) -> StaticDataResponse:
    _check_access(requesting_owner, owner_id)
    await _resolve_account(session, owner_id, body.account_id)

    # Use April 1 of the fiscal year start as the transaction date
    fy_start_year = int(body.fiscal_year.split("-")[0])
    tx_date = date(fy_start_year, 4, 1).isoformat()

    transactions = [
        {
            "transaction_date": tx_date,
            "amount": body.tax_paid_paise,
            "transaction_type": "DEBIT",
            "description": f"Income tax paid — FY {body.fiscal_year}",
            "category": "TAX",
            "metadata": {
                "fiscal_year": body.fiscal_year,
                "gross_income_paise": body.gross_income_paise,
                "taxable_income_paise": body.taxable_income_paise,
                "tds_paise": body.tds_paise,
                "itr_filed": body.itr_filed,
                "deductions_80c_paise": body.deductions_80c_paise,
                "deductions_80d_paise": body.deductions_80d_paise,
            },
        }
    ]
    return await _ingest(owner_id, body.account_id, DocumentType.TAX, transactions)
