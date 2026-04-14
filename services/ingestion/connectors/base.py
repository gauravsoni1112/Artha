"""
ConnectorABC — abstract base class for all data source connectors.

A connector fetches raw document bytes (or structured payloads) from a source.
It is responsible for authentication, pagination, and rate limiting.
It does NOT parse; it hands off bytes to the ParserFactory.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from libs.schemas.enums import DocumentType, IngestionSource


@dataclass
class FetchedDocument:
    """A single document fetched by a connector."""
    raw_bytes: bytes
    doc_type: DocumentType
    source: IngestionSource
    account_id: uuid.UUID
    suggested_filename: str = ""    # used for file_store naming / logging
    metadata: dict | None = None    # source-specific metadata (Gmail message ID, etc.)
    pdf_passwords: list[str] = field(default_factory=list)  # tried in order; empty = no password


class ConnectorABC(ABC):
    """
    Abstract connector. Each subclass targets one data source.

    Usage:
        connector = GmailConnector(owner_id=..., credentials=...)
        async for doc in connector.fetch():
            await ingestion_service.ingest(doc)
    """

    @abstractmethod
    async def fetch(self, owner_id: uuid.UUID) -> list[FetchedDocument]:
        """
        Fetch all new documents for owner_id.

        Returns a list of FetchedDocument instances.
        Should be idempotent — the IngestionService deduplicates by file_hash.
        """
