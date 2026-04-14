"""
IngestionService — orchestrates the full ingest pipeline per document.

Flow (9 steps):
  1. Document-level deduplication (file_hash)
  2. Persist raw bytes (encrypted, local filesystem)
  3. Parse bytes → list[RawTransaction]
  4. Run ValidationPipeline on each record
  5. Compute source_hash + bulk upsert passed records
  6. Bulk insert quarantined records
  7. Mark document parsed
  8. Update ingestion_run stats
  9. Publish Redis notifications

INVARIANTS enforced here:
  - Amount is always in paise (int), never float
  - source_hash conflict → DO NOTHING (idempotent)
  - Quarantined records never reach the transactions table
  - Quarantine table is never exposed to callers of this service
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import structlog
from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from libs.schemas.db_models import (
    Document,
    IngestionRun,
    Transaction,
    TransactionQuarantine,
)
from libs.schemas.enums import IngestionRunStatus, ParseStatus, TriggerType
from libs.tax_rules.fiscal_year import get_fiscal_year
from libs.telemetry.tracing import start_span
from services.ingestion.connectors.base import FetchedDocument
from services.ingestion.dedup import compute_source_hash
from services.ingestion.parsers.base import ParseError
from services.ingestion.parsers.factory import for_type as parser_for_type
from services.storage.file_store import FileStore
from services.storage.notification import NotificationClient
from services.validation.models import RawTransaction
from services.validation.pipeline import ValidationPipeline

log = structlog.get_logger(__name__)


@dataclass
class IngestionResult:
    run_id: uuid.UUID
    status: str
    records_fetched: int = 0
    records_passed: int = 0
    records_quarantined: int = 0
    skipped_duplicate: bool = False
    error: str | None = None


class IngestionService:
    """
    Orchestrates document ingestion end-to-end.

    Args:
        session: AsyncSession connected to PostgreSQL
        pipeline: ValidationPipeline instance
        file_store: FileStore for encrypted PDF persistence
        notifications: NotificationClient for Redis pub/sub
    """

    def __init__(
        self,
        session: AsyncSession,
        pipeline: ValidationPipeline,
        file_store: FileStore,
        notifications: NotificationClient,
    ) -> None:
        self._session = session
        self._pipeline = pipeline
        self._file_store = file_store
        self._notifications = notifications

    # ── Public entry points ───────────────────────────────────────────────────

    async def run(
        self,
        owner_id: uuid.UUID,
        fetched_doc: FetchedDocument,
        trigger_type: str = TriggerType.ADHOC,
    ) -> IngestionResult:
        """
        Ingest a single FetchedDocument.

        Creates an IngestionRun record and processes the document through the
        full 9-step pipeline.
        """
        run_id = uuid.uuid4()
        run = IngestionRun(
            id=run_id,
            source=fetched_doc.source,
            trigger_type=trigger_type,
            status=IngestionRunStatus.RUNNING,
        )
        self._session.add(run)
        await self._session.flush()

        with start_span("ingest_document", {"source": fetched_doc.source, "doc_type": fetched_doc.doc_type}):
            try:
                result = await self._ingest(owner_id, fetched_doc, run_id)
            except Exception as exc:
                log.error("ingestion.unexpected_error", run_id=str(run_id), error=str(exc))
                await self._fail_run(run_id, str(exc))
                await self._session.commit()
                return IngestionResult(
                    run_id=run_id, status=IngestionRunStatus.FAILED, error=str(exc)
                )

        await self._session.commit()
        return result

    # ── Internal pipeline ─────────────────────────────────────────────────────

    async def _ingest(
        self,
        owner_id: uuid.UUID,
        fetched_doc: FetchedDocument,
        run_id: uuid.UUID,
    ) -> IngestionResult:
        raw_bytes = fetched_doc.raw_bytes

        # ── Step 1: Document-level deduplication ──────────────────
        file_hash = hashlib.sha256(raw_bytes).hexdigest()
        existing = await self._session.scalar(
            select(Document.id).where(Document.file_hash == file_hash)
        )
        if existing:
            log.info("ingestion.duplicate_document", file_hash=file_hash)
            await self._update_run(
                run_id,
                status=IngestionRunStatus.SUCCESS,
                records_fetched=0,
                records_passed=0,
                records_quarantined=0,
            )
            return IngestionResult(run_id=run_id, status="DUPLICATE", skipped_duplicate=True)

        # ── Step 2: Persist raw bytes (encrypted) ─────────────────
        file_path = await self._file_store.save(
            raw_bytes,
            owner_id=owner_id,
            file_hash=file_hash,
            filename=fetched_doc.suggested_filename,
        )
        doc = Document(
            id=uuid.uuid4(),
            owner_id=owner_id,
            account_id=fetched_doc.account_id,
            source=fetched_doc.source,
            doc_type=fetched_doc.doc_type,
            file_path=file_path,
            file_hash=file_hash,
            fetched_at=_utcnow(),
            parse_status=ParseStatus.PENDING,
        )
        self._session.add(doc)
        await self._session.flush()

        # ── Step 3: Parse ─────────────────────────────────────────
        parser = parser_for_type(fetched_doc.doc_type)
        candidate_passwords: list[str | None] = list(fetched_doc.pdf_passwords) or [None]
        raw_transactions: list[RawTransaction] | None = None
        last_parse_error: Exception | None = None
        with start_span("parse_document", {"parser": parser.source_name}):
            for pw in candidate_passwords:
                try:
                    raw_transactions = parser.parse(
                        raw_bytes,
                        owner_id,
                        fetched_doc.account_id,
                        password=pw,
                    )
                    break
                except ParseError as exc:
                    last_parse_error = exc
                    log.warning(
                        "ingestion.parse_attempt_failed",
                        parser=parser.source_name,
                        had_password=pw is not None,
                        error=str(exc),
                    )
        if raw_transactions is None:
            raise last_parse_error or ParseError("Parser returned no result")
        log.info("ingestion.parsed", count=len(raw_transactions), parser=parser.source_name)
        await self._update_run(run_id, records_fetched=len(raw_transactions))

        # ── Step 4 + 5 + 6: Validate → pass/quarantine ────────────
        passed_rows, quarantine_rows = await self._validate_and_split(
            raw_transactions, run_id, doc.id
        )

        # ── Step 5: Bulk upsert passed (idempotent) ────────────────
        inserted = 0
        if passed_rows:
            inserted = await self._bulk_upsert_transactions(passed_rows)

        # ── Step 6: Bulk insert quarantined ───────────────────────
        if quarantine_rows:
            self._session.add_all(quarantine_rows)
            await self._session.flush()

        # ── Step 7: Mark document parsed ──────────────────────────
        await self._session.execute(
            update(Document)
            .where(Document.id == doc.id)
            .values(parse_status=ParseStatus.SUCCESS, parsed_at=_utcnow())
        )

        # ── Step 8: Update run stats ───────────────────────────────
        final_status = (
            IngestionRunStatus.SUCCESS
            if not quarantine_rows
            else IngestionRunStatus.PARTIAL
        )
        await self._update_run(
            run_id,
            records_passed=inserted,
            records_quarantined=len(quarantine_rows),
            status=final_status,
            completed_at=_utcnow(),
        )

        # ── Step 9: Notify via Redis ───────────────────────────────
        await self._notifications.publish_ingestion_status(
            run_id=run_id,
            passed=inserted,
            quarantined=len(quarantine_rows),
            document_id=doc.id,
        )
        if quarantine_rows:
            await self._notifications.publish_quarantine_alert(
                count=len(quarantine_rows), document_id=doc.id
            )

        log.info(
            "ingestion.complete",
            run_id=str(run_id),
            passed=inserted,
            quarantined=len(quarantine_rows),
        )
        return IngestionResult(
            run_id=run_id,
            status=final_status,
            records_fetched=len(raw_transactions),
            records_passed=inserted,
            records_quarantined=len(quarantine_rows),
        )

    async def _validate_and_split(
        self,
        raw_transactions: list[RawTransaction],
        run_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> tuple[list[Transaction], list[TransactionQuarantine]]:
        """Run ValidationPipeline; split into passed ORM rows and quarantine ORM rows."""
        passed: list[Transaction] = []
        quarantined: list[TransactionQuarantine] = []

        for raw_tx in raw_transactions:
            result = self._pipeline.run(raw_tx)
            if result.passed:
                record = result.record
                tx_date = record.transaction_date
                passed.append(
                    Transaction(
                        id=uuid.uuid4(),
                        owner_id=record.owner_id,
                        account_id=record.account_id,
                        source_hash=compute_source_hash(
                            record.owner_id,
                            record.account_id,
                            tx_date,
                            record.amount_paise,
                            record.transaction_type,
                            record.description,
                        ),
                        transaction_date=tx_date,
                        value_date=record.value_date,
                        amount_paise=record.amount_paise,  # INVARIANT: always int paise
                        transaction_type=record.transaction_type,
                        category=record.category,
                        description=record.description,
                        raw_description=record.raw_description,
                        merchant=record.merchant,
                        fiscal_year=get_fiscal_year(tx_date),
                        currency=record.currency,
                        document_id=document_id,
                        ingestion_run_id=run_id,
                    )
                )
            else:
                quarantined.append(
                    TransactionQuarantine(
                        id=uuid.uuid4(),
                        ingestion_run_id=run_id,
                        document_id=document_id,
                        raw_data=raw_tx.model_dump(mode="json"),
                        failure_stage=result.failed_stage,
                        failure_reasons=result.errors,
                        raw_amount_text=raw_tx.raw_amount_text,
                        raw_date_text=raw_tx.raw_date_text,
                    )
                )

        return passed, quarantined

    async def _bulk_upsert_transactions(self, transactions: list[Transaction]) -> int:
        """
        Bulk-upsert transactions using ON CONFLICT (source_hash) DO NOTHING.
        Returns the count of actually inserted rows.
        """
        if not transactions:
            return 0

        rows = [
            {
                "id": tx.id,
                "owner_id": tx.owner_id,
                "account_id": tx.account_id,
                "source_hash": tx.source_hash,
                "transaction_date": tx.transaction_date,
                "value_date": tx.value_date,
                "amount_paise": tx.amount_paise,
                "transaction_type": tx.transaction_type,
                "category": tx.category,
                "description": tx.description,
                "raw_description": tx.raw_description,
                "merchant": tx.merchant,
                "fiscal_year": tx.fiscal_year,
                "currency": tx.currency,
                "document_id": tx.document_id,
                "ingestion_run_id": tx.ingestion_run_id,
            }
            for tx in transactions
        ]

        stmt = pg_insert(Transaction.__table__).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["source_hash"])
        result = await self._session.execute(stmt)
        return result.rowcount

    async def _update_run(self, run_id: uuid.UUID, **kwargs) -> None:
        await self._session.execute(
            update(IngestionRun).where(IngestionRun.id == run_id).values(**kwargs)
        )

    async def _fail_run(self, run_id: uuid.UUID, error_message: str) -> None:
        await self._update_run(
            run_id,
            status=IngestionRunStatus.FAILED,
            error_message=error_message,
            completed_at=_utcnow(),
        )


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)
