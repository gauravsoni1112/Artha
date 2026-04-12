"""
BaseParser ABC — every document parser must implement this interface.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from services.validation.models import RawTransaction


class BaseParser(ABC):
    """
    Abstract base class for all document parsers.

    Subclasses implement parse() to extract a list of RawTransaction objects
    from raw document bytes (PDF or structured payload).
    """

    @abstractmethod
    def parse(
        self,
        raw_bytes: bytes,
        owner_id: uuid.UUID,
        account_id: uuid.UUID,
    ) -> list[RawTransaction]:
        """
        Parse raw document bytes into a list of RawTransaction objects.

        Args:
            raw_bytes: raw PDF bytes (or JSON/YAML bytes for manual parsers)
            owner_id: UUID of the owning family member
            account_id: UUID of the source account

        Returns:
            List of RawTransaction instances (may be empty if no transactions found).

        Raises:
            ParseError: if the document cannot be parsed at all.
        """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable name for logging (e.g. "HDFC Bank Statement")."""


class ParseError(Exception):
    """Raised when a parser cannot process the given document."""
