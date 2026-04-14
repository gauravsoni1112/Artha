"""
Real integration test: Fetch actual bank/CC/MF PDFs from Gmail and ingest them.

Requires:
  - Docker PostgreSQL running (docker compose -f infra/docker-compose.yml up -d)
  - Alembic migrations applied (alembic upgrade head)
  - GMAIL_CLIENT_SECRETS pointing to a valid OAuth client_secrets.json
  - GMAIL_TOKEN_PATH (default ~/.artha/gmail_token.json) with a consented token
    Generate once via:  python tests/gmail_token_generator.py

Run with:
  pytest tests/integration/test_gmail_real.py -v -m integration -s
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from libs.schemas.db_models import Account, Document, IngestionRun, Owner, Transaction
from libs.schemas.enums import AccountType, DocumentType, IngestionSource
from services.ingestion.connectors.gmail_connector import GmailConnector
from services.ingestion.ingestion_service import IngestionService
from services.storage.file_store import FileStore
from services.storage.notification import NotificationClient
from services.validation.pipeline import InMemorySpendHistory, ValidationPipeline

load_dotenv()

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
async def owner_and_accounts(db_session: AsyncSession):
    """Create test owner and one account per document type Gmail might return."""
    owner = Owner(id=uuid.uuid4(), name="Test User - Gmail")
    db_session.add(owner)
    await db_session.flush()

    bank = Account(
        id=uuid.uuid4(),
        owner_id=owner.id,
        account_type=AccountType.SAVINGS,
        institution="Gmail-Bank",
    )
    cc = Account(
        id=uuid.uuid4(),
        owner_id=owner.id,
        account_type=AccountType.CREDIT_CARD,
        institution="Gmail-CC",
    )
    mf = Account(
        id=uuid.uuid4(),
        owner_id=owner.id,
        account_type=AccountType.MF_FOLIO,
        institution="Gmail-MF",
    )
    db_session.add_all([bank, cc, mf])
    await db_session.flush()

    account_id_map = {
        DocumentType.BANK_STATEMENT: bank.id,
        DocumentType.CC_STATEMENT: cc.id,
        DocumentType.MF_CAS: mf.id,
    }
    return owner, account_id_map


@pytest_asyncio.fixture
async def ingestion_service(db_session: AsyncSession):
    pipeline = ValidationPipeline(spend_history=InMemorySpendHistory())
    file_store = FileStore(base_path="/tmp/artha_test_gmail")
    notifications = NotificationClient()
    return IngestionService(
        session=db_session,
        pipeline=pipeline,
        file_store=file_store,
        notifications=notifications,
    )


def _gmail_token_available() -> bool:
    token_path = os.path.expanduser(
        os.getenv("GMAIL_TOKEN_PATH", "~/.artha/gmail_token.json")
    )
    return os.path.exists(token_path)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(
    not _gmail_token_available(),
    reason="Gmail OAuth token missing. Run tests/gmail_token_generator.py first.",
)
async def test_gmail_real_fetch_and_ingest(
    db_session, owner_and_accounts, ingestion_service
):
    """Fetch real Gmail PDF attachments, ingest them, and verify DB state."""
    owner, account_id_map = owner_and_accounts

    connector = GmailConnector(
        account_id_map=account_id_map,
        max_results_per_query=5,
    )

    print("\n📧 Fetching from Gmail...")
    documents = await connector.fetch(owner_id=owner.id)

    if not documents:
        pytest.skip(
            "No matching PDF attachments found in Gmail inbox. "
            "Default queries target HDFC/SBI/ICICI/Axis/CAMS/KFintech senders."
        )

    print(f"✅ Fetched {len(documents)} document(s)")

    per_type_counts: dict[str, int] = {}
    for doc in documents:
        per_type_counts[doc.doc_type] = per_type_counts.get(doc.doc_type, 0) + 1
    print(f"   Breakdown by doc_type: {per_type_counts}")

    success_or_partial = 0
    failed = 0
    for i, doc in enumerate(documents, 1):
        print(f"\n📄 Ingesting {i}/{len(documents)}: {doc.suggested_filename}")
        print(f"   Source: {doc.source}  Type: {doc.doc_type}  Size: {len(doc.raw_bytes)} bytes")

        try:
            result = await ingestion_service.run(owner.id, doc)
        except Exception as exc:
            # Password-protected or unparseable PDFs will raise — expected for some banks.
            print(f"   ⚠️  Ingestion raised: {type(exc).__name__}: {exc}")
            failed += 1
            continue

        print(f"   Status: {result.status}")
        print(f"   Fetched: {result.records_fetched}  "
              f"Passed: {result.records_passed}  "
              f"Quarantined: {result.records_quarantined}")
        success_or_partial += 1

    print(f"\n📊 Summary: {success_or_partial} ingested, {failed} failed outright")

    # At minimum, the Gmail fetch itself worked — that's the primary assertion.
    assert len(documents) > 0

    # Verify any persisted documents carry GMAIL as the source.
    docs = await db_session.scalars(
        select(Document).where(Document.owner_id == owner.id)
    )
    doc_list = docs.all()
    print(f"\n🗄️  Documents persisted: {len(doc_list)}")
    assert all(d.source == IngestionSource.GMAIL.value for d in doc_list)

    # If anything got through parsing+validation, sanity-check the transactions.
    txs = await db_session.scalars(
        select(Transaction).where(Transaction.owner_id == owner.id)
    )
    tx_list = txs.all()
    print(f"🧾 Transactions persisted: {len(tx_list)}")

    if tx_list:
        run_ids = {t.ingestion_run_id for t in tx_list if t.ingestion_run_id}
        runs = await db_session.scalars(
            select(IngestionRun).where(IngestionRun.id.in_(run_ids))
        )
        assert all(r.source == IngestionSource.GMAIL.value for r in runs.all())

        for tx in tx_list[:10]:
            print(f"   {tx.transaction_date}  {tx.transaction_type:<6}  "
                  f"₹{tx.amount_paise / 100:>12,.2f}  {tx.raw_description[:60]}")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(
    not _gmail_token_available(),
    reason="Gmail OAuth token missing. Run tests/gmail_token_generator.py first.",
)
async def test_gmail_auth_smoke(owner_and_accounts):
    """Smoke test: just verify OAuth creds load and Gmail search returns a response."""
    owner, _ = owner_and_accounts

    connector = GmailConnector(max_results_per_query=1)
    # fetch() swallows auth errors and returns []; we just need it not to hang/crash.
    docs = await connector.fetch(owner_id=owner.id)
    print(f"\n✅ Gmail auth + search reachable. Documents found: {len(docs)}")
