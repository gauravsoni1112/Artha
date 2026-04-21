# Agent Tools Reference

This document describes all available tools the Artha agent can use to answer user questions.

## Account & Transaction Tools

### `fetch_accounts`
**Purpose**: Retrieve all bank accounts for the user

**Parameters**:
- `owner_id` (required): UUID of the owner
- `account_type` (optional): Filter by account type (BANK, CREDIT_CARD, INVESTMENT)

**Returns**:
- List of accounts with:
  - Account ID (UUID)
  - Type (BANK, CREDIT_CARD, INVESTMENT, etc.)
  - Institution (e.g., HDFC, ICICI, Zerodha)
  - Nickname (custom name or fallback to "Institution Type")
  - Active status
  - Transaction count for each account

**Example**: "Show me all my bank accounts" or "What accounts do I have?"

### `transaction_query`
**Purpose**: Fetch transactions with optional filters

**Parameters**:
- `owner_id` (required): UUID of the owner
- `start_date` (optional): YYYY-MM-DD format
- `end_date` (optional): YYYY-MM-DD format
- `category` (optional): Transaction category filter (e.g., GROCERIES)
- `account_id` (optional): Filter by specific account UUID
- `limit` (optional): Max rows to return (default: 50)

**Returns**:
- List of transactions with amounts in both paise and INR
- Summary of total credits, debits, and net

**Example**: "Show me transactions from my HDFC account in June" or "Find all grocery expenses"

## Analytics Tools

### `category_analysis`
Analyse spending by category over a time period.

### `spending_trend`
Month-over-month spending trends for categories.

### `budget_comparison`
Compare actual spending vs. budget targets.

## Financial Summary Tools

### `net_worth`
Compute total net worth (all holdings + accounts - liabilities).

### `portfolio_value`
Summarise investment portfolio by asset class.

### `tax_summary`
ITR/tax summary per fiscal year.

### `upcoming_expenses`
Predict recurring expenses based on transaction history.

### `goal_progress`
Query financial goals and compute progress.

## Risk & Insurance Tools

### `asset_concentration`
Portfolio concentration by asset class.

### `debt_to_income`
Debt-to-income ratio analysis.

### `insurance_coverage_gap`
Life and health insurance coverage gap estimation.

### `emergency_fund_months`
Emergency fund coverage in months.

## Utility/Math Tools

### `convert_amount`
Convert INR amounts between denominations (paise, rupee, lakh, crore).

### `calculate_percentage`
Compute percentage of an amount.

### `calculate_growth`
Compute absolute and percentage change.

### `calculate_compound_interest`
Calculate compound interest on investments.

---

## Usage Pattern

The agent follows this reasoning protocol:

1. **Thought**: Brief reasoning about what tools are needed
2. **Action**: Call the appropriate tool(s)
3. **Observation**: Receive and summarize the tool result
4. **Final Answer**: Provide the answer to the user

For account-specific queries, the agent typically:
1. Calls `fetch_accounts` to list available accounts
2. Calls `transaction_query` with the specific `account_id` to get transactions
3. Uses other analytics tools as needed
