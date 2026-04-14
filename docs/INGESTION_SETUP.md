# Ingestion Setup Guide

This guide explains how to set up and configure each data source connector for the Artha ingestion system.

## Table of Contents

1. [Gmail Connector Setup](#gmail-connector-setup)
2. [Zerodha Connector Setup](#zerodha-connector-setup)
3. [Manual Connector Setup](#manual-connector-setup)
4. [Testing Your Setup](#testing-your-setup)
5. [Troubleshooting](#troubleshooting)

---

## Gmail Connector Setup

The Gmail connector fetches financial PDFs (bank statements, credit card statements, mutual fund CAS) from your Gmail inbox using the Gmail API.

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (Name: "Artha" or similar)
3. Enable the **Gmail API**:
   - Search for "Gmail API" in the search bar
   - Click **Enable**

### Step 2: Create OAuth2 Credentials

1. Go to **Credentials** in the left sidebar
2. Click **Create Credentials** → **OAuth 2.0 Client ID**
3. Choose **Desktop application** as the application type
4. Download the credentials JSON file and save it to a secure location:
   ```bash
   # Example path
   cp ~/Downloads/client_secret_*.json ~/.artha/gmail_credentials.json
   ```

### Step 3: Configure Environment

Edit your `.env` file:

```bash
GMAIL_CLIENT_SECRETS=~/.artha/gmail_credentials.json
GMAIL_TOKEN_PATH=~/.artha/gmail_token.json
```

### Step 4: First-Run OAuth2 Consent Flow

When you run ingestion for the first time:

1. The API will open your browser to the Google consent screen
2. Sign in with the Gmail account containing your financial PDFs
3. Grant Artha permission to read emails and attachments (**Read-only**)
4. The token is automatically saved to `GMAIL_TOKEN_PATH`

**Note:** The consent happens once. The token will be automatically refreshed when it expires.

### Step 5: Verify Setup

```bash
# Test manual ingestion endpoint to verify credentials work
curl -X POST http://localhost:8000/ingest/GMAIL?owner_id=<your-owner-uuid> \
  -H "Content-Type: application/json"
```

You should see a response with ingestion run details.

### Security Notes

- ✅ **OAuth2 tokens** are stored locally in `~/.artha/` (never sent to Artha servers)
- ✅ **Read-only scope** — Artha only reads attachments, never modifies emails
- ✅ **Automatic refresh** — Token is refreshed silently before expiry
- ⚠️ **Keep credentials file secure** — Don't commit `gmail_credentials.json` to version control

---

## Zerodha Connector Setup

The Zerodha connector fetches equity holdings and trade history from your Zerodha demat account.

### Prerequisites

- Active Zerodha trading account
- Kite API access enabled (free, requires 2-factor authentication)

### Step 1: Get API Credentials from Zerodha

1. Log in to [Zerodha Kite](https://kite.zerodha.com)
2. Go to **Account** → **API Tokens** (or visit https://kite.zerodha.com/account/tokens)
3. Generate a new API key:
   - Click **Generate Key**
   - You'll see:
     - **API Key** (keep safe)
     - **Access Token** (expires daily — see Step 2)

### Step 2: Get Daily Access Token

⚠️ **Important:** Zerodha access tokens expire after one trading day. You have two options:

**Option A: Manual Refresh (Recommended for Testing)**
1. Go to [Kite Login](https://kite.zerodha.com/api/login)
2. Log in with 2FA
3. Copy the `access_token` from the redirect URL query parameter
4. Update `.env`:
   ```bash
   ZERODHA_ACCESS_TOKEN=<copied-token>
   ```

**Option B: Automated Token Refresh (For Production)**
Set up a daily job to refresh the token:
```bash
# Schedule daily token refresh
# This would typically be handled by a cron job or task scheduler
# that retrieves a new access token and updates the environment
```

### Step 3: Configure Environment

Edit your `.env` file:

```bash
ZERODHA_API_KEY=your_kite_api_key
ZERODHA_ACCESS_TOKEN=your_kite_access_token
ZERODHA_LOOKBACK_DAYS=90  # optional, default: 90
```

### Step 4: Verify Setup

```bash
# Test Zerodha ingestion
curl -X POST "http://localhost:8000/ingest/ZERODHA_API?owner_id=<your-owner-uuid>&account_id=<zerodha-account-uuid>" \
  -H "Content-Type: application/json"
```

You should see holdings and trades fetched.

### Data Captured

- **Holdings:** Current equity positions with market value
- **Trade History:** Buy/Sell transactions from last N days (default: 90)
- **Metadata:** ISIN, quantity, average price, exchange

### Security Notes

- ✅ **Access token** is stored locally (never sent outside your system)
- ✅ **API key + token** are only used for API calls to Zerodha
- ⚠️ **Token expires daily** — set up automated refresh for production
- ⚠️ **2FA required** — maintain it for your Zerodha account

---

## Manual Connector Setup

The Manual connector allows you to inject structured JSON data directly into Artha. Use this for:

- Insurance policies
- Real estate holdings
- Gold/precious metals
- Tax payments
- Any custom financial data

### API Endpoint

```bash
POST /ingest/MANUAL
```

### Request Format

```json
{
  "owner_id": "550e8400-e29b-41d4-a716-446655440000",
  "account_id": "550e8400-e29b-41d4-a716-446655440001",
  "doc_type": "OTHER",
  "transactions": [
    {
      "date": "15/06/2024",
      "description": "Insurance Premium Payment",
      "amount": "5000.00",
      "type": "DEBIT",
      "category": "INSURANCE"
    },
    {
      "date": "01/06/2024",
      "description": "Gold Purchase",
      "amount": "25000.00",
      "type": "DEBIT",
      "category": "INVESTMENT"
    }
  ]
}
```

### Document Types

- `OTHER` — Default, for general transactions
- `INSURANCE` — Insurance premiums, claims
- `TAX` — Tax payments, refunds
- `BANK_STATEMENT` — Not typically used (use Gmail connector instead)
- `CC_STATEMENT` — Not typically used (use Gmail connector instead)
- `MF_CAS` — Not typically used (use Gmail connector instead)

### Transaction Field Format

| Field       | Type   | Format              | Example                          |
|-----------|--------|------------------|--------------------------------|
| date      | string | DD/MM/YYYY       | "15/06/2024"                   |
| description | string | Any text         | "Insurance Premium"            |
| amount    | string | Numeric, with commas for lakhs | "1,00,000.00" or "5000" |
| type      | string | DEBIT or CREDIT  | "DEBIT"                        |
| category  | string | Transaction category | "INSURANCE", "INVESTMENT"    |

### Example: Using cURL

```bash
curl -X POST http://localhost:8000/ingest/MANUAL \
  -H "Content-Type: application/json" \
  -d '{
    "owner_id": "550e8400-e29b-41d4-a716-446655440000",
    "account_id": "550e8400-e29b-41d4-a716-446655440001",
    "doc_type": "INSURANCE",
    "transactions": [
      {
        "date": "15/06/2024",
        "description": "Health Insurance Premium",
        "amount": "5000.00",
        "type": "DEBIT",
        "category": "INSURANCE"
      }
    ]
  }'
```

---

## Testing Your Setup

### Run Unit Tests

```bash
# All ingestion tests
pytest tests/unit/ingestion/ -v

# Specific connector
pytest tests/unit/ingestion/connectors/test_gmail_connector.py -v
pytest tests/unit/ingestion/connectors/test_zerodha_connector.py -v
pytest tests/unit/ingestion/connectors/test_manual_connector.py -v
```

### Run Integration Tests (Requires Docker)

```bash
# Start infrastructure
docker compose -f infra/docker-compose.yml up -d

# Run migrations
alembic upgrade head

# Run integration tests
pytest tests/integration/test_ingestion_flow.py -v -m integration
```

### Test Endpoints Manually

```bash
# List recent ingestion runs
curl http://localhost:8000/ingestion-runs?limit=10

# Get specific run details
curl http://localhost:8000/ingestion-runs/<run-id>
```

---

## Troubleshooting

### Gmail Issues

**Problem:** "Gmail client_secrets.json not found"
- **Solution:** Download credentials from Google Cloud Console and set `GMAIL_CLIENT_SECRETS` in `.env`

**Problem:** "Failed to fetch messages"
- **Solution:** Verify Gmail API is enabled in your Google Cloud project
- Check if your Gmail account has the financial PDFs with expected attachments

**Problem:** Token expired
- **Solution:** Delete `~/.artha/gmail_token.json` and re-run. The consent flow will trigger again.

### Zerodha Issues

**Problem:** "ZERODHA_API_KEY and ZERODHA_ACCESS_TOKEN must be set"
- **Solution:** Set both env vars from Step 1 above

**Problem:** "Invalid access_token"
- **Solution:** The token expires daily. Get a fresh one from Kite login page
- Visit https://kite.zerodha.com/api/login and copy the new token

**Problem:** "No trades found"
- **Solution:** Check if you have actual trades in the last 90 days
- Adjust `ZERODHA_LOOKBACK_DAYS` if needed

### General Issues

**Problem:** "Database connection failed"
- **Solution:** Ensure PostgreSQL is running: `docker compose -f infra/docker-compose.yml ps`

**Problem:** "Test database locked"
- **Solution:** Kill any stray pytest processes: `pkill -f pytest`

**Problem:** "Transactions not appearing in DB"
- **Solution:** Check `transaction_quarantine` table for validation errors
- Run: `SELECT * FROM transaction_quarantine ORDER BY created_at DESC LIMIT 10;`

---

## Next Steps

1. ✅ Set up at least one connector (Gmail recommended for beginners)
2. ✅ Run unit tests to verify configuration
3. ✅ Test the API endpoint manually
4. ✅ Monitor ingestion runs via `/ingestion-runs` endpoint
5. ✅ Check `transaction_quarantine` for any validation issues

For Phase 4 (Multi-Agent System), ensure all three connectors are working smoothly before starting.
