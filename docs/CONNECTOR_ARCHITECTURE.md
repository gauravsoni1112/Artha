# Connector Architecture Guide

This document describes the design and extensibility of the Artha ingestion connector system.

## Overview

The connector system fetches financial documents from various sources (Gmail, Zerodha, manual) and transforms them into a unified `FetchedDocument` format that the `IngestionService` can process.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                   IngestionService                          │
│  Orchestrates 9-step pipeline (validation, dedup, persist)  │
└────────────────┬────────────────────────────────────────────┘
                 │
       ┌─────────┴────────┬────────────────────┐
       │                  │                    │
       ▼                  ▼                    ▼
   ┌─────────────┐  ┌──────────────┐   ┌──────────────┐
   │    Gmail    │  │   Zerodha    │   │    Manual    │
   │ Connector   │  │  Connector   │   │  Connector   │
   └─────────────┘  └──────────────┘   └──────────────┘
       │                  │                    │
       └─────────────────┬────────────────────┘
                         │
           ┌─────────────┴──────────────┐
           │   ConnectorABC (abstract)  │
           │  - async fetch()           │
           │  → list[FetchedDocument]  │
           └────────────────────────────┘
                         ▲
           ┌─────────────┴──────────────┐
           │      FetchedDocument       │
           │  - raw_bytes              │
           │  - doc_type               │
           │  - source                 │
           │  - account_id             │
           │  - suggested_filename     │
           │  - metadata (optional)    │
           └────────────────────────────┘
                         │
       ┌─────────────────┴────────────────┐
       ▼                                  ▼
 ┌──────────────┐              ┌─────────────────┐
 │   Parsers    │              │  ValidationPipeline │
 │  (factory)   │              │  (4 stages)      │
 └──────────────┘              └─────────────────┘
       │
       ▼
 ┌──────────────────────┐
 │   RawTransaction     │
 │  (validated)         │
 └──────────────────────┘
```

---

## Core Components

### 1. ConnectorABC (Abstract Base Class)

```python
# services/ingestion/connectors/base.py

class ConnectorABC(ABC):
    @abstractmethod
    async def fetch(self, owner_id: UUID) -> list[FetchedDocument]:
        """Fetch all new documents for the given owner."""
        pass
```

**Responsibilities:**
- Authenticate with external API/service
- Query for new documents
- Download/fetch raw bytes
- Transform to `FetchedDocument` instances
- Handle errors gracefully (return empty list, not exceptions)

**Key constraint:** Connectors are **idempotent** — the `IngestionService` deduplicates via `file_hash`, so re-running a connector is safe.

### 2. FetchedDocument (Data Class)

```python
@dataclass
class FetchedDocument:
    raw_bytes: bytes                          # Document bytes (PDF, JSON, etc.)
    doc_type: DocumentType                    # BANK_STATEMENT, CC_STATEMENT, MF_CAS, etc.
    source: IngestionSource                   # GMAIL, ZERODHA_API, MANUAL, etc.
    account_id: UUID                          # Which account owns this document
    suggested_filename: str = ""              # For logging/storage
    metadata: dict | None = None              # Source-specific data (e.g., Gmail msg ID)
```

---

## Existing Connectors

### Gmail Connector

**File:** `services/ingestion/connectors/gmail_connector.py`

**Features:**
- OAuth2 authentication (local token storage)
- Configurable Gmail search queries per document type
- PDF extraction from email attachments
- Graceful error handling (missing emails, API failures)

**Flow:**
1. Load OAuth2 credentials (or trigger consent flow)
2. For each configured query (bank statement, CC, CAS):
   - Search Gmail for matching emails
   - Fetch each email and extract PDF attachments
   - Return list of `FetchedDocument` with raw PDF bytes

**Configuration:**
```bash
GMAIL_CLIENT_SECRETS=path/to/credentials.json
GMAIL_TOKEN_PATH=~/.artha/gmail_token.json
```

**Queries (customizable):**
- Bank statements: `from:statements@hdfcbank.net has:attachment filename:pdf`
- Credit cards: `from:credit_card@hdfcbank.net has:attachment filename:pdf`
- Mutual funds: `from:noreply@camsonline.com has:attachment filename:pdf`

---

### Zerodha Connector

**File:** `services/ingestion/connectors/zerodha_connector.py`

**Features:**
- Kite Connect API integration
- Holdings and trade history fetching
- JSON transformation to transaction format
- Lookback filtering for trades

**Flow:**
1. Initialize KiteConnect client with API key + access token
2. Fetch holdings → transform to JSON → return as `FetchedDocument`
3. Fetch trades (last N days) → transform to JSON → return as `FetchedDocument`

**Configuration:**
```bash
ZERODHA_API_KEY=your_kite_api_key
ZERODHA_ACCESS_TOKEN=your_access_token  # Expires daily!
ZERODHA_LOOKBACK_DAYS=90
```

**Output Format:**
```json
[
  {
    "date": "2024-06-15",
    "description": "Holding: INFY (NSE)",
    "amount": "15005.00",
    "type": "CREDIT",
    "category": "INVESTMENT",
    "extra": {
      "isin": "INE009A01021",
      "quantity": 10,
      "last_price": 1500.50
    }
  }
]
```

---

### Manual Connector

**File:** `services/ingestion/connectors/manual_connector.py`

**Features:**
- Wraps pre-formed JSON payload into `FetchedDocument`
- No external API calls
- Used for user-entered data (insurance, real estate, etc.)

**Flow:**
1. Accept pre-formed JSON bytes
2. Wrap in `FetchedDocument` with specified doc_type and account_id
3. Return single-element list

**Input Format:**
```json
{
  "transactions": [
    {
      "date": "15/06/2024",
      "description": "Insurance Premium",
      "amount": "5000.00",
      "type": "DEBIT",
      "category": "INSURANCE"
    }
  ]
}
```

---

## Creating a New Connector

To add a new data source (e.g., a third-party stock broker, insurance API), follow these steps:

### 1. Create the Connector Class

```python
# services/ingestion/connectors/my_source_connector.py

from services.ingestion.connectors.base import ConnectorABC, FetchedDocument

class MySourceConnector(ConnectorABC):
    def __init__(self, api_key: str | None = None, ...):
        self._api_key = api_key or os.getenv("MY_SOURCE_API_KEY", "")
        # ... other init

    async def fetch(self, owner_id: UUID) -> list[FetchedDocument]:
        """
        Fetch documents from MySource API.
        
        Returns:
            List of FetchedDocument instances.
            On error, return empty list (don't raise exception).
        """
        try:
            api_client = self._init_client()
        except Exception as exc:
            log.error("my_source.auth_failed", error=str(exc))
            return []

        documents = []
        
        try:
            # Fetch from API
            items = api_client.get_items()
            
            # Transform to FetchedDocument
            for item in items:
                documents.append(
                    FetchedDocument(
                        raw_bytes=item.to_bytes(),
                        doc_type=DocumentType.OTHER,
                        source=IngestionSource.MY_SOURCE,  # Add to enums
                        account_id=self._map_account(item),
                        suggested_filename=f"my_source_{item.id}.json",
                        metadata={"item_id": item.id},
                    )
                )
        except Exception as exc:
            log.warning("my_source.fetch_failed", error=str(exc))
        
        log.info("my_source.fetch_complete", owner_id=str(owner_id), documents=len(documents))
        return documents
```

### 2. Register the Source Enum

Edit `libs/schemas/enums.py`:

```python
class IngestionSource(str, Enum):
    # ... existing sources
    MY_SOURCE = "MY_SOURCE"
```

### 3. Create Unit Tests

```python
# tests/unit/ingestion/connectors/test_my_source_connector.py

@pytest.mark.asyncio
async def test_my_source_connector_fetch(mock_api_client, test_owner_id):
    connector = MySourceConnector(api_key="test_key")
    docs = await connector.fetch(test_owner_id)
    
    assert len(docs) > 0
    assert docs[0].source == IngestionSource.MY_SOURCE
```

### 4. Create API Endpoint (Optional)

Add to `api/routers/ingestion.py`:

```python
@router.post("/MY_SOURCE", response_model=list[IngestResponse])
async def ingest_my_source(owner_id: UUID = Query(...)):
    connector = MySourceConnector()
    documents = await connector.fetch(owner_id)
    
    results = []
    async with get_ingestion_service() as svc:
        for doc in documents:
            result = await svc.run(owner_id, doc, trigger_type=TriggerType.ADHOC)
            results.append(IngestResponse(...))
    return results
```

### 5. Document Configuration

Add to `docs/INGESTION_SETUP.md` with setup instructions for your source.

---

## Design Principles

### 1. **Idempotency**
- Connectors can be run multiple times safely
- `IngestionService` deduplicates via `file_hash` (SHA-256 of raw bytes)
- If the same document is fetched again, it's skipped

### 2. **Graceful Error Handling**
- Connectors catch exceptions and log them
- **Always return empty list, never raise exceptions**
- This allows one failing connector to not block others

### 3. **Authentication Isolation**
- Each connector manages its own authentication
- Credentials stored locally, never exposed in logs
- Token refresh handled within connector

### 4. **Separation of Concerns**
- Connector: Fetch and fetch only (no parsing, no validation)
- Parser: Transform bytes → `RawTransaction` objects
- ValidationPipeline: Validate, quarantine, or pass

### 5. **Extensibility**
- New connectors just inherit from `ConnectorABC`
- New document types added to enum
- No changes to core `IngestionService`

---

## Best Practices

### For Connector Authors

1. **Log diagnostics** at INFO/WARNING levels (structlog):
   ```python
   log.info("my_source.auth_success", user=user_id)
   log.warning("my_source.api_limit_reached")
   log.error("my_source.critical_failure", error=str(exc))
   ```

2. **Handle missing environment variables gracefully**:
   ```python
   api_key = os.getenv("MY_SOURCE_API_KEY", "")
   if not api_key:
       log.warning("my_source.missing_api_key")
       return []
   ```

3. **Test with mocks, not real APIs**:
   - Use `unittest.mock.MagicMock` or `@patch` decorator
   - Mock entire API responses
   - Test error paths (auth failure, rate limits, timeouts)

4. **Document configuration and setup**:
   - Add to `.env.example`
   - Write setup guide in `docs/INGESTION_SETUP.md`
   - Explain how to get credentials

### For Testing

1. **Create fixtures in `tests/unit/ingestion/conftest.py`**:
   ```python
   @pytest.fixture
   def mock_api_response():
       return {...}  # Standard test data
   ```

2. **Test both happy path and error cases**:
   - Valid data
   - Empty results
   - API failures
   - Auth failures
   - Malformed responses

3. **Use parametrized tests for multiple scenarios**:
   ```python
   @pytest.mark.parametrize("doc_type,expected", [
       (DocumentType.BANK_STATEMENT, "bank"),
       (DocumentType.CC_STATEMENT, "cc"),
   ])
   async def test_fetch(doc_type, expected):
       ...
   ```

---

## Running Connectors

### Via API Endpoints

```bash
# Gmail
curl -X POST http://localhost:8000/ingest/GMAIL?owner_id=<uuid>

# Zerodha
curl -X POST "http://localhost:8000/ingest/ZERODHA_API?owner_id=<uuid>&account_id=<uuid>"

# Manual
curl -X POST http://localhost:8000/ingest/MANUAL \
  -H "Content-Type: application/json" \
  -d '{"owner_id": "...", "transactions": [...]}'
```

### Programmatically

```python
from services.ingestion.connectors.gmail_connector import GmailConnector
from services.ingestion.ingestion_service import IngestionService

connector = GmailConnector()
docs = await connector.fetch(owner_id)

async with get_ingestion_service() as svc:
    for doc in docs:
        result = await svc.run(owner_id, doc)
        print(result.status)
```

---

## Monitoring & Debugging

### Check Ingestion Runs

```sql
SELECT id, source, trigger_type, status, records_fetched, records_passed, 
       records_quarantined, started_at, completed_at
FROM ingestion_runs
ORDER BY started_at DESC
LIMIT 20;
```

### Check Quarantined Transactions

```sql
SELECT id, document_id, failure_stage, failure_reasons, raw_data
FROM transaction_quarantine
WHERE ingestion_run_id = '<run-id>'
ORDER BY created_at DESC;
```

### Enable Debug Logging

```python
# Increase log verbosity in test
import structlog
structlog.configure(
    processors=[
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)
```

---

## Future Enhancements

- [ ] Scheduled connector runs (via APScheduler)
- [ ] Automatic token refresh for Zerodha (daily cron)
- [ ] Connector rate limiting (respect API quotas)
- [ ] Retry logic with exponential backoff
- [ ] Connector health dashboard
- [ ] Multi-source deduplication (same transaction from multiple sources)
