"""
Deduplication — compute the source_hash idempotency key for transactions.

source_hash = SHA-256( "|".join([owner_id, account_id, date, amount_paise, type, description]) )

This key is stored as a UNIQUE constraint on transactions.source_hash.
Duplicate documents ingested via different runs will silently skip already-seen
transactions via ON CONFLICT (source_hash) DO NOTHING.
"""

import hashlib
import uuid
from datetime import date


def compute_source_hash(
    owner_id: uuid.UUID,
    account_id: uuid.UUID,
    transaction_date: date,
    amount_paise: int,
    transaction_type: str,
    description: str,
) -> str:
    """
    Compute a stable SHA-256 hash that uniquely identifies a transaction.

    Args:
        owner_id: UUID of the owning family member
        account_id: UUID of the source account
        transaction_date: parsed transaction date
        amount_paise: signed paise integer (negative = debit)
        transaction_type: "CREDIT" or "DEBIT"
        description: normalised description string

    Returns:
        64-character hex string (SHA-256 digest)
    """
    parts = [
        str(owner_id),
        str(account_id),
        transaction_date.isoformat(),
        str(amount_paise),
        transaction_type.upper(),
        description.strip().lower(),
    ]
    payload = "|".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
