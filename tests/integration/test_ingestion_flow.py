"""
Integration test: full ingestion flow (PDF bytes → transactions table).

Requires:
  - Docker Desktop running
  - PostgreSQL 16 container up (infra/docker-compose.yml)
  - Alembic migrations applied (alembic upgrade head)

Run with:
  pytest tests/integration/ -v
"""

from __future__ import annotations

import json
import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from libs.schemas.db_models import (
    Account,
    IngestionRun,
    Owner,
    Transaction,
    TransactionQuarantine,
)
from libs.schemas.enums import AccountType, DocumentType, IngestionSource
from services.ingestion.connectors.base import FetchedDocument
from services.ingestion.ingestion_service import IngestionService
from services.storage.file_store import FileStore
from services.storage.notification import NotificationClient
from services.validation.pipeline import InMemorySpendHistory, ValidationPipeline

# ── Fixtures ──────────────────────────────────────────────────────────────────

TEST_DB_URL = "postgresql+asyncpg://artha:artha_secret@localhost:5432/artha"


@pytest.fixture(scope="session")
def event_loop_policy():
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Provide a test DB session that rolls back after each test."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as session:
        yield session
        await session.rollback()

    await engine.dispose()


@pytest_asyncio.fixture
async def owner_and_account(db_session: AsyncSession):
    """Create a test owner and account."""
    owner = Owner(id=uuid.uuid4(), name="Test Owner")
    db_session.add(owner)
    await db_session.flush()

    account = Account(
        id=uuid.uuid4(),
        owner_id=owner.id,
        account_type=AccountType.SAVINGS,
        institution="HDFC",
    )
    db_session.add(account)
    await db_session.flush()

    return owner, account


@pytest_asyncio.fixture
async def ingestion_service(db_session: AsyncSession):
    """Construct a fully wired IngestionService for testing."""
    pipeline = ValidationPipeline(spend_history=InMemorySpendHistory())
    file_store = FileStore(base_path="/tmp/artha_test")
    notifications = NotificationClient()
    # Don't connect Redis in tests — notifications are best-effort
    return IngestionService(
        session=db_session,
        pipeline=pipeline,
        file_store=file_store,
        notifications=notifications,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_manual_payload(transactions: list[dict]) -> bytes:
    return json.dumps({"transactions": transactions}).encode()


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.integration
async def test_manual_ingest_happy_path(db_session, owner_and_account, ingestion_service):
    """Valid transactions should be inserted into the transactions table."""
    owner, account = owner_and_account
    payload = _make_manual_payload([
        {
            "date": "15/06/2024",
            "description": "SALARY CREDIT",
            "amount": "1,00,000.00",
            "type": "CREDIT",
            "category": "SALARY",
        },
        {
            "date": "01/06/2024",
            "description": "Grocery Shopping BigBasket",
            "amount": "2,500.00",
            "type": "DEBIT",
        },
    ])

    fetched = FetchedDocument(
        raw_bytes=payload,
        doc_type=DocumentType.OTHER,
        source=IngestionSource.MANUAL,
        account_id=account.id,
    )

    result = await ingestion_service.run(owner.id, fetched)

    assert result.status in ("SUCCESS", "PARTIAL")
    assert result.records_fetched == 2
    assert result.records_passed == 2
    assert result.records_quarantined == 0

    # Verify rows in DB
    rows = await db_session.scalars(
        select(Transaction).where(Transaction.owner_id == owner.id)
    )
    txs = rows.all()
    assert len(txs) == 2

    salary_tx = next((t for t in txs if "SALARY" in t.raw_description.upper()), None)
    assert salary_tx is not None
    assert salary_tx.amount_paise == 10000000  # ₹1,00,000 = 1,00,00,000 paise? No: 1,00,000 rupees = 10,000,000 paise
    assert salary_tx.transaction_type == "CREDIT"
    assert salary_tx.fiscal_year == "2024-25"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_duplicate_document_skipped(db_session, owner_and_account, ingestion_service):
    """Ingesting the same document twice should skip the second run."""
    owner, account = owner_and_account
    payload = _make_manual_payload([
        {"date": "01/06/2024", "description": "Test Tx", "amount": "100", "type": "DEBIT"}
    ])

    fetched = FetchedDocument(
        raw_bytes=payload,
        doc_type=DocumentType.OTHER,
        source=IngestionSource.MANUAL,
        account_id=account.id,
    )

    result1 = await ingestion_service.run(owner.id, fetched)
    result2 = await ingestion_service.run(owner.id, fetched)

    assert result1.status != "DUPLICATE"
    assert result2.status == "DUPLICATE"
    assert result2.skipped_duplicate is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_invalid_transaction_quarantined(db_session, owner_and_account, ingestion_service):
    """Transactions with future dates should end up in quarantine."""
    owner, account = owner_and_account
    payload = _make_manual_payload([
        {
            "date": "01/01/2099",  # future date
            "description": "Future Payment",
            "amount": "500.00",
            "type": "DEBIT",
        }
    ])

    fetched = FetchedDocument(
        raw_bytes=payload,
        doc_type=DocumentType.OTHER,
        source=IngestionSource.MANUAL,
        account_id=account.id,
    )

    result = await ingestion_service.run(owner.id, fetched)

    assert result.records_quarantined == 1
    assert result.records_passed == 0

    quarantine_rows = await db_session.scalars(
        select(TransactionQuarantine).where(
            TransactionQuarantine.ingestion_run_id == result.run_id
        )
    )
    qrows = quarantine_rows.all()
    assert len(qrows) == 1
    assert qrows[0].failure_stage == "RANGE"
    assert qrows[0].quarantine_status == "PENDING_REVIEW"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_idempotent_source_hash(db_session, owner_and_account, ingestion_service):
    """Two different documents with the same transaction should not duplicate it."""
    owner, account = owner_and_account
    tx_data = {
        "date": "10/06/2024",
        "description": "Idempotent Test",
        "amount": "750.00",
        "type": "DEBIT",
    }

    payload1 = _make_manual_payload([tx_data])
    # Different raw_bytes (different file_hash) but same logical transaction
    payload2 = json.dumps({"transactions": [tx_data], "meta": "second_run"}).encode()

    for payload in [payload1, payload2]:
        await ingestion_service.run(
            owner.id,
            FetchedDocument(
                raw_bytes=payload,
                doc_type=DocumentType.OTHER,
                source=IngestionSource.MANUAL,
                account_id=account.id,
            ),
        )

    # Should have exactly 1 transaction row (not 2)
    rows = await db_session.scalars(
        select(Transaction).where(
            Transaction.owner_id == owner.id,
            Transaction.raw_description == "Idempotent Test",
        )
    )
    assert len(rows.all()) == 1
