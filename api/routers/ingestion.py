"""
Ingestion API Router.

Endpoints:
  POST /ingest/MANUAL          — trigger manual ingestion of a JSON transaction payload
  POST /ingest/GMAIL           — trigger ad-hoc Gmail ingestion
  POST /ingest/ZERODHA_API     — trigger ad-hoc Zerodha ingestion
  GET  /ingestion-runs         — list recent ingestion runs
  GET  /ingestion-runs/{id}    — get a specific run's details
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_session
from api.dependencies import get_ingestion_service
from libs.schemas.db_models import IngestionRun
from libs.schemas.enums import DocumentType, IngestionSource, TriggerType
from services.ingestion.connectors.manual_connector import ManualConnector
import json

router = APIRouter(prefix="/ingest", tags=["ingestion"])


# ── Request / Response models ─────────────────────────────────────────────────

class ManualIngestRequest(BaseModel):
    owner_id: uuid.UUID
    account_id: uuid.UUID
    doc_type: DocumentType = DocumentType.OTHER
    transactions: list[dict]


class IngestResponse(BaseModel):
    run_id: uuid.UUID
    status: str
    records_fetched: int
    records_passed: int
    records_quarantined: int
    skipped_duplicate: bool = False


class IngestionRunSummary(BaseModel):
    id: uuid.UUID
    source: str
    trigger_type: str
    status: str
    records_fetched: int
    records_passed: int
    records_quarantined: int
    started_at: str
    completed_at: str | None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/MANUAL", response_model=IngestResponse)
async def ingest_manual(body: ManualIngestRequest):
    """
    Ingest a manually-provided list of transactions.

    Accepts insurance premiums, real estate data, gold purchases,
    tax payments, or any structured financial transaction.
    """
    payload_bytes = json.dumps({"transactions": body.transactions}).encode()
    connector = ManualConnector(
        payload_bytes=payload_bytes,
        doc_type=body.doc_type,
        account_id=body.account_id,
    )

    async with get_ingestion_service() as svc:
        documents = await connector.fetch(body.owner_id)
        if not documents:
            raise HTTPException(status_code=400, detail="No documents to ingest")

        result = await svc.run(body.owner_id, documents[0], trigger_type=TriggerType.ADHOC)

    return IngestResponse(
        run_id=result.run_id,
        status=result.status,
        records_fetched=result.records_fetched,
        records_passed=result.records_passed,
        records_quarantined=result.records_quarantined,
        skipped_duplicate=result.skipped_duplicate,
    )


@router.post("/GMAIL", response_model=list[IngestResponse])
async def ingest_gmail(owner_id: uuid.UUID = Query(...)):
    """
    Trigger ad-hoc Gmail ingestion for the given owner.
    Fetches all matching PDF attachments and processes them.
    """
    from services.ingestion.connectors.gmail_connector import GmailConnector

    connector = GmailConnector()
    documents = await connector.fetch(owner_id)

    if not documents:
        return []

    results = []
    async with get_ingestion_service() as svc:
        for doc in documents:
            result = await svc.run(owner_id, doc, trigger_type=TriggerType.ADHOC)
            results.append(
                IngestResponse(
                    run_id=result.run_id,
                    status=result.status,
                    records_fetched=result.records_fetched,
                    records_passed=result.records_passed,
                    records_quarantined=result.records_quarantined,
                    skipped_duplicate=result.skipped_duplicate,
                )
            )
    return results


@router.post("/ZERODHA_API", response_model=list[IngestResponse])
async def ingest_zerodha(owner_id: uuid.UUID = Query(...), account_id: uuid.UUID = Query(...)):
    """
    Trigger ad-hoc Zerodha ingestion (holdings + trades).
    Requires ZERODHA_API_KEY and ZERODHA_ACCESS_TOKEN to be set.
    """
    from services.ingestion.connectors.zerodha_connector import ZerodhaConnector

    connector = ZerodhaConnector(account_id=account_id)
    documents = await connector.fetch(owner_id)

    results = []
    async with get_ingestion_service() as svc:
        for doc in documents:
            result = await svc.run(owner_id, doc, trigger_type=TriggerType.ADHOC)
            results.append(
                IngestResponse(
                    run_id=result.run_id,
                    status=result.status,
                    records_fetched=result.records_fetched,
                    records_passed=result.records_passed,
                    records_quarantined=result.records_quarantined,
                )
            )
    return results


# ── Ingestion run history ─────────────────────────────────────────────────────

ingestion_runs_router = APIRouter(prefix="/ingestion-runs", tags=["ingestion"])


@ingestion_runs_router.get("", response_model=list[IngestionRunSummary])
async def list_ingestion_runs(
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """List the most recent ingestion runs."""
    rows = await session.scalars(
        select(IngestionRun).order_by(desc(IngestionRun.started_at)).limit(limit)
    )
    runs = rows.all()
    return [
        IngestionRunSummary(
            id=r.id,
            source=r.source,
            trigger_type=r.trigger_type,
            status=r.status,
            records_fetched=r.records_fetched,
            records_passed=r.records_passed,
            records_quarantined=r.records_quarantined,
            started_at=r.started_at.isoformat(),
            completed_at=r.completed_at.isoformat() if r.completed_at else None,
        )
        for r in runs
    ]


@ingestion_runs_router.get("/{run_id}", response_model=IngestionRunSummary)
async def get_ingestion_run(
    run_id: uuid.UUID = Path(...),
    session: AsyncSession = Depends(get_session),
):
    """Get details for a specific ingestion run."""
    run = await session.get(IngestionRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Ingestion run {run_id} not found")
    return IngestionRunSummary(
        id=run.id,
        source=run.source,
        trigger_type=run.trigger_type,
        status=run.status,
        records_fetched=run.records_fetched,
        records_passed=run.records_passed,
        records_quarantined=run.records_quarantined,
        started_at=run.started_at.isoformat(),
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
    )
