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
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from libs.schemas.db_models import (
    Account,
    Document,
    IngestionRun,
    Owner,
    Transaction,
    TransactionQuarantine,
)
from libs.schemas.enums import AccountType, DocumentType, IngestionRunStatus, IngestionSource
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
    """Provide a test DB session that rolls back after each test.

    Uses a nested transaction (savepoint) so that commits inside the
    service code commit to the savepoint rather than the real DB.
    The outer transaction is rolled back after the test, leaving the
    database unchanged.
    """
    engine = create_async_engine(TEST_DB_URL, echo=False)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)

        # Redirect session.commit() to a nested savepoint so the
        # outer transaction can still be rolled back.
        @event.listens_for(session.sync_session, "after_transaction_end")
        def restart_savepoint(db_session, transaction):
            if transaction.nested and not transaction._parent.nested:
                session.sync_session.begin_nested()

        await conn.begin_nested()

        yield session

        await session.close()
        await trans.rollback()

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


# ── Tests: Gmail Connector Integration ────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.integration
async def test_gmail_connector_integration_happy_path(db_session, owner_and_account, ingestion_service, sample_bank_pdf_bytes):
    """Gmail-sourced PDF should ingest successfully through full pipeline."""
    from services.ingestion.connectors.base import FetchedDocument

    owner, account = owner_and_account

    # Use proper minimal valid PDF from fixture
    pdf_bytes = sample_bank_pdf_bytes

    fetched = FetchedDocument(
        raw_bytes=pdf_bytes,
        doc_type=DocumentType.BANK_STATEMENT,
        source=IngestionSource.GMAIL,
        account_id=account.id,
        suggested_filename="hdfc_statement_jun_2024.pdf",
        metadata={"gmail_message_id": "mock_msg_123"},
    )

    # Ingest should complete, though parsing may fail (no real PDF)
    # The document should be persisted and marked for parsing
    result = await ingestion_service.run(owner.id, fetched)

    assert result.run_id is not None
    assert result.status in (IngestionRunStatus.SUCCESS, IngestionRunStatus.PARTIAL, "PARTIAL")

    # Document should exist in DB
    doc = await db_session.scalar(
        select(Document).where(Document.owner_id == owner.id)
    )
    assert doc is not None
    assert doc.source == IngestionSource.GMAIL
    assert doc.doc_type == DocumentType.BANK_STATEMENT


@pytest.mark.asyncio
@pytest.mark.integration
async def test_gmail_connector_multiple_documents(db_session, owner_and_account, ingestion_service, sample_bank_pdf_bytes):
    """Multiple Gmail documents should ingest independently."""
    from services.ingestion.connectors.base import FetchedDocument

    owner, account = owner_and_account

    # Create two different PDFs to avoid deduplication
    # Modify the stream slightly to have different file hashes
    pdf_bytes_1 = sample_bank_pdf_bytes.replace(b"Mock Bank Statement", b"HDFC June 2024")
    pdf_bytes_2 = sample_bank_pdf_bytes.replace(b"Mock Bank Statement", b"HDFC July 2024")

    # Ingest two bank statements with different content
    fetched1 = FetchedDocument(
        raw_bytes=pdf_bytes_1,
        doc_type=DocumentType.BANK_STATEMENT,
        source=IngestionSource.GMAIL,
        account_id=account.id,
        suggested_filename="hdfc_jun.pdf",
    )

    fetched2 = FetchedDocument(
        raw_bytes=pdf_bytes_2,
        doc_type=DocumentType.BANK_STATEMENT,
        source=IngestionSource.GMAIL,
        account_id=account.id,
        suggested_filename="hdfc_july.pdf",
    )

    result1 = await ingestion_service.run(owner.id, fetched1)
    result2 = await ingestion_service.run(owner.id, fetched2)

    # Both should complete
    assert result1.run_id is not None
    assert result2.run_id is not None
    assert result1.run_id != result2.run_id

    # Both documents should exist
    docs = await db_session.scalars(
        select(Document).where(
            Document.owner_id == owner.id,
            Document.source == IngestionSource.GMAIL,
        )
    )
    assert len(docs.all()) == 2


# ── Tests: Zerodha Connector Integration ──────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.integration
async def test_zerodha_connector_integration_holdings(db_session, owner_and_account, ingestion_service):
    """Zerodha holdings payload should ingest successfully."""
    from services.ingestion.connectors.base import FetchedDocument

    owner, account = owner_and_account

    # Simulate holdings response
    holdings_payload = json.dumps([
        {
            "date": date.today().isoformat(),
            "description": "Holding: INFY (NSE)",
            "amount": "15005.00",
            "type": "CREDIT",
            "category": "INVESTMENT",
            "merchant": "Zerodha",
            "extra": {
                "isin": "INE009A01021",
                "quantity": 10,
                "last_price": 1500.50,
            },
        }
    ]).encode()

    fetched = FetchedDocument(
        raw_bytes=holdings_payload,
        doc_type=DocumentType.OTHER,
        source=IngestionSource.ZERODHA_API,
        account_id=account.id,
        suggested_filename="zerodha_holdings_2024-06-15.json",
    )

    result = await ingestion_service.run(owner.id, fetched)

    assert result.status in (IngestionRunStatus.SUCCESS, IngestionRunStatus.PARTIAL, "SUCCESS", "PARTIAL")
    assert result.records_fetched == 1

    # Transaction should be created
    tx = await db_session.scalar(
        select(Transaction).where(
            Transaction.owner_id == owner.id,
            Transaction.description.like("%INFY%"),
        )
    )
    assert tx is not None
    assert tx.amount_paise == int(15005.00 * 100)  # 1500500 paise (quantity * price)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_zerodha_connector_integration_trades(db_session, owner_and_account, ingestion_service):
    """Zerodha trade history payload should ingest successfully."""
    from services.ingestion.connectors.base import FetchedDocument

    owner, account = owner_and_account

    # Simulate trades response
    trades_payload = json.dumps([
        {
            "date": date.today().isoformat(),
            "description": "Trade: INFY BUY",
            "amount": "14500.00",
            "type": "DEBIT",
            "category": "INVESTMENT",
            "merchant": "Zerodha",
        }
    ]).encode()

    fetched = FetchedDocument(
        raw_bytes=trades_payload,
        doc_type=DocumentType.OTHER,
        source=IngestionSource.ZERODHA_API,
        account_id=account.id,
        suggested_filename="zerodha_trades_2024-06-15.json",
    )

    result = await ingestion_service.run(owner.id, fetched)

    assert result.status in (IngestionRunStatus.SUCCESS, IngestionRunStatus.PARTIAL, "SUCCESS", "PARTIAL")
    assert result.records_fetched == 1

    # Transaction should be created
    tx = await db_session.scalar(
        select(Transaction).where(
            Transaction.owner_id == owner.id,
            Transaction.description.like("%INFY%"),
        )
    )
    assert tx is not None


# ── Tests: Multi-source ingestion ─────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.integration
async def test_multi_source_ingest_single_run(db_session, owner_and_account, ingestion_service):
    """Multiple sources (Manual + Zerodha) should ingest in single run."""
    from services.ingestion.connectors.base import FetchedDocument

    owner, account = owner_and_account

    # Manual: insurance payment
    manual_payload = json.dumps({
        "transactions": [
            {
                "date": "15/06/2024",
                "description": "Insurance Premium",
                "amount": "5000.00",
                "type": "DEBIT",
                "category": "INSURANCE",
            }
        ]
    }).encode()

    # Zerodha: holding
    zerodha_payload = json.dumps([
        {
            "date": date.today().isoformat(),
            "description": "Holding: TCS (NSE)",
            "amount": "19000.00",
            "type": "CREDIT",
            "category": "INVESTMENT",
            "merchant": "Zerodha",
        }
    ]).encode()

    manual_doc = FetchedDocument(
        raw_bytes=manual_payload,
        doc_type=DocumentType.INSURANCE,
        source=IngestionSource.MANUAL,
        account_id=account.id,
    )

    zerodha_doc = FetchedDocument(
        raw_bytes=zerodha_payload,
        doc_type=DocumentType.OTHER,
        source=IngestionSource.ZERODHA_API,
        account_id=account.id,
    )

    result1 = await ingestion_service.run(owner.id, manual_doc)
    result2 = await ingestion_service.run(owner.id, zerodha_doc)

    assert result1.status in (IngestionRunStatus.SUCCESS, IngestionRunStatus.PARTIAL, "SUCCESS", "PARTIAL")
    assert result2.status in (IngestionRunStatus.SUCCESS, IngestionRunStatus.PARTIAL, "SUCCESS", "PARTIAL")

    # Both transactions should exist
    txs = await db_session.scalars(
        select(Transaction).where(Transaction.owner_id == owner.id)
    )
    assert len(txs.all()) >= 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_duplicate_across_sources(db_session, owner_and_account, ingestion_service):
    """Same transaction from different sources should be idempotent."""
    from services.ingestion.connectors.base import FetchedDocument

    owner, account = owner_and_account

    # Same transaction via Manual and Zerodha (different source_hash due to different ingestion runs)
    # But same logical data
    payload1 = json.dumps({
        "transactions": [
            {
                "date": "10/06/2024",
                "description": "Same Transaction",
                "amount": "1000.00",
                "type": "DEBIT",
            }
        ]
    }).encode()

    payload2 = json.dumps([
        {
            "date": "10/06/2024",
            "description": "Same Transaction",
            "amount": "1000.00",
            "type": "DEBIT",
        }
    ]).encode()

    doc1 = FetchedDocument(
        raw_bytes=payload1,
        doc_type=DocumentType.OTHER,
        source=IngestionSource.MANUAL,
        account_id=account.id,
    )

    doc2 = FetchedDocument(
        raw_bytes=payload2,
        doc_type=DocumentType.OTHER,
        source=IngestionSource.ZERODHA_API,
        account_id=account.id,
    )

    await ingestion_service.run(owner.id, doc1)
    await ingestion_service.run(owner.id, doc2)

    # Should have 1 transaction (same source_hash)
    txs = await db_session.scalars(
        select(Transaction).where(
            Transaction.owner_id == owner.id,
            Transaction.description == "Same Transaction",
        )
    )
    assert len(txs.all()) == 1
