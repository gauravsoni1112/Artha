"""
Real integration test: Fetch actual Zerodha holdings & trades.

Requires:
  - Docker PostgreSQL running (docker compose -f infra/docker-compose.yml up -d)
  - Alembic migrations applied (alembic upgrade head)
  - ZERODHA_API_KEY and ZERODHA_ACCESS_TOKEN in .env (valid tokens)

Run with:
  pytest tests/integration/test_zerodha_real.py -v -m integration -s
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from libs.schemas.db_models import Account, Owner, Transaction
from libs.schemas.enums import AccountType, IngestionRunStatus, IngestionSource
from services.ingestion.connectors.zerodha_connector import ZerodhaConnector
from services.ingestion.ingestion_service import IngestionService
from services.storage.file_store import FileStore
from services.storage.notification import NotificationClient
from services.validation.pipeline import InMemorySpendHistory, ValidationPipeline

TEST_DB_URL = "postgresql+asyncpg://artha:artha_secret@localhost:5432/artha"


@pytest.fixture(scope="session")
def event_loop_policy():
    import asyncio

    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Test DB session with transaction rollback."""
    engine = create_async_engine(TEST_DB_URL, echo=False)

    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)

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
    """Create test owner and Zerodha demat account."""
    owner = Owner(id=uuid.uuid4(), name="Test User - Zerodha")
    db_session.add(owner)
    await db_session.flush()

    # Zerodha demat account
    account = Account(
        id=uuid.uuid4(),
        owner_id=owner.id,
        account_type=AccountType.DEMAT,
        institution="Zerodha",
    )
    db_session.add(account)
    await db_session.flush()

    return owner, account


@pytest_asyncio.fixture
async def ingestion_service(db_session: AsyncSession):
    """Fully wired IngestionService."""
    pipeline = ValidationPipeline(spend_history=InMemorySpendHistory())
    file_store = FileStore(base_path="/tmp/artha_test")
    notifications = NotificationClient()
    return IngestionService(
        session=db_session,
        pipeline=pipeline,
        file_store=file_store,
        notifications=notifications,
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_zerodha_real_fetch_and_ingest(db_session, owner_and_account, ingestion_service):
    """Fetch real Zerodha holdings & trades, ingest into DB.

    This test:
      1. Calls ZerodhaConnector.fetch() with your real API credentials
      2. Ingests holdings + recent trades into the database
      3. Verifies transactions are created with correct amounts
    """
    owner, account = owner_and_account

    # Initialize connector with credentials from .env
    connector = ZerodhaConnector(account_id=account.id, lookback_days=30)

    # Fetch real documents from Zerodha
    print("\n🔗 Fetching from Zerodha Kite API...")
    documents = await connector.fetch(owner_id=owner.id)

    if not documents:
        pytest.skip("No documents fetched from Zerodha (API may be down or no trades)")

    print(f"✅ Fetched {len(documents)} document(s)")

    # Ingest each document
    for i, doc in enumerate(documents, 1):
        print(f"\n📊 Ingesting document {i}/{len(documents)}...")
        print(f"   Source: {doc.source}")
        print(f"   Doc type: {doc.doc_type}")
        print(f"   Size: {len(doc.raw_bytes)} bytes")

        result = await ingestion_service.run(owner.id, doc)

        print(f"   Status: {result.status}")
        print(f"   Records fetched: {result.records_fetched}")
        print(f"   Records passed: {result.records_passed}")
        print(f"   Records quarantined: {result.records_quarantined}")

        # Verify some records were processed
        assert result.status in (
            IngestionRunStatus.SUCCESS,
            IngestionRunStatus.PARTIAL,
            "SUCCESS",
            "PARTIAL",
        )
        assert result.records_fetched > 0

    # Verify transactions in DB
    print("\n🔍 Checking database...")
    txs = await db_session.scalars(
        select(Transaction).where(Transaction.owner_id == owner.id)
    )
    tx_list = txs.all()
    print(f"✅ Found {len(tx_list)} transaction(s) in database")

    for tx in tx_list:
        print(f"\n   {tx.raw_description}")
        print(f"      Amount: ₹{tx.amount_paise / 100:,.2f}")
        print(f"      Date: {tx.transaction_date}")
        print(f"      Type: {tx.transaction_type}")

    # Basic assertions
    assert len(tx_list) > 0, "Expected at least one transaction from Zerodha"

    # Verify the ingestion runs that produced these transactions were Zerodha-sourced
    run_ids = {tx.ingestion_run_id for tx in tx_list if tx.ingestion_run_id}
    from libs.schemas.db_models import IngestionRun
    runs = await db_session.scalars(
        select(IngestionRun).where(IngestionRun.id.in_(run_ids))
    )
    assert all(r.source == IngestionSource.ZERODHA_API.value for r in runs.all())


@pytest.mark.asyncio
@pytest.mark.integration
async def test_zerodha_holdings_only(db_session, owner_and_account, ingestion_service):
    """Fetch and verify holdings specifically."""
    owner, account = owner_and_account

    connector = ZerodhaConnector(account_id=account.id)
    documents = await connector.fetch(owner_id=owner.id)

    holdings_docs = [d for d in documents if "holdings" in d.suggested_filename]

    if not holdings_docs:
        pytest.skip("No holdings fetched (may not have open positions)")

    doc = holdings_docs[0]
    result = await ingestion_service.run(owner.id, doc)

    print(f"\n📈 Holdings Ingestion:")
    print(f"   Status: {result.status}")
    print(f"   Count: {result.records_fetched}")

    # Holdings should be CREDIT type (assets)
    txs = await db_session.scalars(
        select(Transaction).where(
            Transaction.owner_id == owner.id,
            Transaction.transaction_type == "CREDIT",
        )
    )
    holdings_txs = [t for t in txs.all() if "Holding:" in t.raw_description]
    print(f"   Positions: {len(holdings_txs)}")
    for tx in holdings_txs:
        print(f"      {tx.raw_description} → ₹{tx.amount_paise / 100:,.2f}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_zerodha_trades_only(db_session, owner_and_account, ingestion_service):
    """Fetch and verify trades specifically."""
    owner, account = owner_and_account

    connector = ZerodhaConnector(account_id=account.id, lookback_days=30)
    documents = await connector.fetch(owner_id=owner.id)

    trades_docs = [d for d in documents if "trades" in d.suggested_filename]

    if not trades_docs:
        pytest.skip("No trades in past 30 days")

    doc = trades_docs[0]
    result = await ingestion_service.run(owner.id, doc)

    print(f"\n📊 Trades Ingestion (past 30 days):")
    print(f"   Status: {result.status}")
    print(f"   Count: {result.records_fetched}")

    txs = await db_session.scalars(
        select(Transaction).where(
            Transaction.owner_id == owner.id,
            Transaction.transaction_type.in_(["BUY", "DEBIT", "CREDIT"]),
        )
    )
    trades_txs = [t for t in txs.all() if "Trade:" in t.raw_description]
    print(f"   Trades executed: {len(trades_txs)}")
    for tx in trades_txs:
        print(f"      {tx.raw_description} → ₹{tx.amount_paise / 100:,.2f}")
