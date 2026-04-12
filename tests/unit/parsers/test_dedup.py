"""Unit tests for services/ingestion/dedup.py"""

import uuid
from datetime import date

from services.ingestion.dedup import compute_source_hash


class TestComputeSourceHash:
    def _hash(self, **kwargs):
        defaults = {
            "owner_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
            "account_id": uuid.UUID("00000000-0000-0000-0000-000000000002"),
            "transaction_date": date(2024, 6, 15),
            "amount_paise": -50000,
            "transaction_type": "DEBIT",
            "description": "neft transfer",
        }
        defaults.update(kwargs)
        return compute_source_hash(**defaults)

    def test_returns_64_char_hex(self):
        h = self._hash()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_same_inputs_same_hash(self):
        assert self._hash() == self._hash()

    def test_different_amount_different_hash(self):
        assert self._hash(amount_paise=-50000) != self._hash(amount_paise=-60000)

    def test_different_date_different_hash(self):
        h1 = self._hash(transaction_date=date(2024, 6, 15))
        h2 = self._hash(transaction_date=date(2024, 6, 16))
        assert h1 != h2

    def test_different_description_different_hash(self):
        h1 = self._hash(description="neft transfer")
        h2 = self._hash(description="salary credit")
        assert h1 != h2

    def test_description_case_normalised(self):
        # Description is lower-cased and stripped before hashing
        h1 = self._hash(description="NEFT Transfer")
        h2 = self._hash(description="neft transfer")
        assert h1 == h2

    def test_different_owner_different_hash(self):
        h1 = self._hash(owner_id=uuid.uuid4())
        h2 = self._hash(owner_id=uuid.uuid4())
        assert h1 != h2
