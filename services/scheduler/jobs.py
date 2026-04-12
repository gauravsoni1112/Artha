"""
Scheduled job definitions for Artha ingestion.

Jobs are registered at application startup (api/main.py).
Each job runs at a configured cron schedule and can also be triggered
ad-hoc via the POST /ingest/{source} API endpoint.

Schedule overview:
  - gmail_ingest    : daily at 07:00 (after banks send overnight statements)
  - zerodha_ingest  : daily at 09:30 (after NSE/BSE market open + EOD data)

Jobs are idempotent — the IngestionService deduplicates by file_hash.
"""

from __future__ import annotations

import os
import uuid

import structlog

from services.scheduler.scheduler import get_scheduler

log = structlog.get_logger(__name__)


# ── Job: Gmail ingestion ──────────────────────────────────────────────────────

async def run_gmail_ingestion() -> None:
    """
    Fetch all PDF attachments from Gmail and ingest them.
    Runs daily at 07:00.
    """
    log.info("job.gmail_ingestion.started")
    try:
        from services.ingestion.connectors.gmail_connector import GmailConnector
        from api.dependencies import get_ingestion_service

        owner_id = uuid.UUID(os.environ["ARTHA_OWNER_ID"])
        connector = GmailConnector()
        documents = await connector.fetch(owner_id)

        async with get_ingestion_service() as svc:
            from libs.schemas.enums import TriggerType
            for doc in documents:
                result = await svc.run(owner_id, doc, trigger_type=TriggerType.SCHEDULED)
                log.info(
                    "job.gmail_ingestion.document_done",
                    status=result.status,
                    passed=result.records_passed,
                    quarantined=result.records_quarantined,
                )
    except Exception as exc:
        log.error("job.gmail_ingestion.failed", error=str(exc))

    log.info("job.gmail_ingestion.completed")


# ── Job: Zerodha ingestion ────────────────────────────────────────────────────

async def run_zerodha_ingestion() -> None:
    """
    Fetch latest holdings and trades from Zerodha and ingest them.
    Runs daily at 09:30.
    """
    log.info("job.zerodha_ingestion.started")
    try:
        from services.ingestion.connectors.zerodha_connector import ZerodhaConnector
        from api.dependencies import get_ingestion_service
        from libs.schemas.enums import TriggerType

        owner_id = uuid.UUID(os.environ["ARTHA_OWNER_ID"])
        account_id = uuid.UUID(os.environ.get("ZERODHA_ACCOUNT_ID", str(uuid.UUID(int=0))))
        connector = ZerodhaConnector(account_id=account_id)
        documents = await connector.fetch(owner_id)

        async with get_ingestion_service() as svc:
            for doc in documents:
                result = await svc.run(owner_id, doc, trigger_type=TriggerType.SCHEDULED)
                log.info(
                    "job.zerodha_ingestion.document_done",
                    status=result.status,
                    passed=result.records_passed,
                )
    except Exception as exc:
        log.error("job.zerodha_ingestion.failed", error=str(exc))

    log.info("job.zerodha_ingestion.completed")


# ── Registration helper ───────────────────────────────────────────────────────

def register_all_jobs() -> None:
    """
    Register all ingestion jobs with the APScheduler.
    Called once at application startup.
    """
    scheduler = get_scheduler()

    # Gmail: daily at 07:00
    scheduler.add_job(
        run_gmail_ingestion,
        trigger="cron",
        hour=7,
        minute=0,
        id="gmail_ingest",
        replace_existing=True,
    )

    # Zerodha: daily at 09:30
    scheduler.add_job(
        run_zerodha_ingestion,
        trigger="cron",
        hour=9,
        minute=30,
        id="zerodha_ingest",
        replace_existing=True,
    )

    log.info("scheduler.jobs_registered", jobs=["gmail_ingest", "zerodha_ingest"])
