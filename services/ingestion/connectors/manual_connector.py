"""
Manual Connector — wraps pre-formed JSON bytes as a FetchedDocument.

Used for:
  - Insurance policies
  - Real estate / gold holdings
  - Tax data entered via the API (POST /ingest/MANUAL)
  - Any static data the user wants to inject
"""

from __future__ import annotations

import uuid

from libs.schemas.enums import DocumentType, IngestionSource
from services.ingestion.connectors.base import ConnectorABC, FetchedDocument


class ManualConnector(ConnectorABC):
    """
    Wraps a pre-formed payload dict/list into a FetchedDocument.

    Args:
        payload_bytes: JSON bytes to inject
        doc_type: DocumentType for this payload
        account_id: UUID of the target account
    """

    def __init__(
        self,
        payload_bytes: bytes,
        doc_type: DocumentType = DocumentType.OTHER,
        account_id: uuid.UUID | None = None,
    ) -> None:
        self._payload = payload_bytes
        self._doc_type = doc_type
        self._account_id = account_id or uuid.UUID(int=0)

    async def fetch(self, owner_id: uuid.UUID) -> list[FetchedDocument]:
        return [
            FetchedDocument(
                raw_bytes=self._payload,
                doc_type=self._doc_type,
                source=IngestionSource.MANUAL,
                account_id=self._account_id,
                suggested_filename=f"manual_{owner_id}.json",
            )
        ]
