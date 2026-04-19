"""
Gmail Connector — fetches bank/CC/MF statement PDFs via Gmail API.

Authentication:
  Uses OAuth2 with the gmail.readonly scope.
  Token is stored locally at GMAIL_TOKEN_PATH (default: ~/.artha/gmail_token.json).
  On first run, triggers the browser OAuth2 consent flow.

Document detection:
  Searches for emails matching configurable Gmail queries per document type.
  Default queries target common Indian bank statement senders.

Privacy:
  Only reads email metadata and attachments — never email body text.
  OAuth token is stored locally and never logged.
"""

from __future__ import annotations

import base64
import hashlib
import os
import uuid
from email.utils import parseaddr
from pathlib import Path

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from libs.schemas.enums import DocumentType, IngestionSource
from services.ingestion.connectors.base import ConnectorABC, FetchedDocument

log = structlog.get_logger(__name__)

# Gmail OAuth2 scope — read-only
_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Default search queries per document type
# These match the most common Indian bank email senders.
_DEFAULT_QUERIES: list[tuple[str, DocumentType]] = [
    # Bank statements
    ("from:statements@hdfcbank.net has:attachment filename:pdf", DocumentType.BANK_STATEMENT),
    ("from:statements@sbi.co.in has:attachment filename:pdf", DocumentType.BANK_STATEMENT),
    ("from:eStatement@icicibank.com has:attachment filename:pdf", DocumentType.BANK_STATEMENT),
    ("from:statement@axisbank.com has:attachment filename:pdf", DocumentType.BANK_STATEMENT),
    # Credit card statements
    ("from:credit_card@hdfcbank.net has:attachment filename:pdf", DocumentType.CC_STATEMENT),
    ("from:creditcard@axisbank.com has:attachment filename:pdf", DocumentType.CC_STATEMENT),
    ("from:cbssbi.cas@alerts.sbi.co.in has:attachment filename:pdf", DocumentType.BANK_STATEMENT),
    ("from:bankstatements@kotak.bank.in has:attachment filename:pdf", DocumentType.BANK_STATEMENT),
    ("from:estatement@icici.bank.in has:attachment filename:pdf", DocumentType.BANK_STATEMENT),
    # Mutual fund CAS
    ("from:noreply@camsonline.com has:attachment filename:pdf", DocumentType.MF_CAS),
    ("from:donotreply@camsonline.com has:attachment filename:pdf", DocumentType.MF_CAS),
    ("from:mfcas@kfintech.com has:attachment filename:pdf", DocumentType.MF_CAS),
    # Subject-based fallback for CAS
    ('subject:"Consolidated Account Statement" has:attachment filename:pdf', DocumentType.MF_CAS),
]


def _passwords_for_sender(sender_email: str) -> list[str]:
    """
    Look up PDF_PASSWORD_<sender_email> in environment.
    Returns a list of candidate passwords (comma-separated in the env value),
    or [] if nothing is configured. Candidates are tried in order.
    """
    if not sender_email:
        return []
    raw = os.getenv(f"PDF_PASSWORD_{sender_email.replace('@', '_AT_')}", "")
    return [p.strip() for p in raw.split(",") if p.strip()]


def _extract_sender(message: dict) -> str:
    """Pull the From header off a Gmail message and return just the email address."""
    headers = message.get("payload", {}).get("headers", []) or []
    for h in headers:
        if h.get("name", "").lower() == "from":
            _, addr = parseaddr(h.get("value", ""))
            return addr.lower()
    return ""


class GmailConnector(ConnectorABC):
    """
    Fetches PDF attachments from Gmail using the Gmail API.

    Args:
        client_secrets_path: Path to OAuth2 client_secrets.json
        token_path: Path where the access/refresh token is persisted
        account_id_map: Maps document_type → account_id (UUID)
        queries: Override the default search queries
        max_results_per_query: Limit emails checked per query (default 10)
    """

    def __init__(
        self,
        client_secrets_path: str | None = None,
        token_path: str | None = None,
        account_id_map: dict[str, uuid.UUID] | None = None,
        queries: list[tuple[str, DocumentType]] | None = None,
        max_results_per_query: int = 10,
    ) -> None:
        self._client_secrets = client_secrets_path or os.getenv("GMAIL_CLIENT_SECRETS", "")
        self._token_path = Path(
            token_path or os.getenv("GMAIL_TOKEN_PATH", "~/.artha/gmail_token.json")
        ).expanduser()
        self._account_id_map = account_id_map or {}
        self._queries = queries or _DEFAULT_QUERIES
        self._max_results = max_results_per_query

    def _get_credentials(self) -> Credentials:
        """Load or refresh OAuth2 credentials, triggering consent flow if needed."""
        creds: Credentials | None = None

        if self._token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self._token_path), _SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self._client_secrets or not Path(self._client_secrets).exists():
                    raise FileNotFoundError(
                        f"Gmail client_secrets.json not found at '{self._client_secrets}'. "
                        "Download it from the Google Cloud Console and set GMAIL_CLIENT_SECRETS."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(self._client_secrets, _SCOPES)
                creds = flow.run_local_server(port=0)

            # Persist token (never log its contents)
            self._token_path.parent.mkdir(parents=True, exist_ok=True)
            self._token_path.write_text(creds.to_json())

        return creds

    async def fetch(self, owner_id: uuid.UUID) -> list[FetchedDocument]:
        """
        Search Gmail for matching emails and return PDF attachments.

        Returns an empty list (not an exception) if no new documents are found.
        """
        try:
            creds = self._get_credentials()
        except Exception as exc:
            log.error("gmail.auth_failed", error=str(exc))
            return []

        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        documents: list[FetchedDocument] = []

        for query, doc_type in self._queries:
            try:
                results = (
                    service.users()
                    .messages()
                    .list(userId="me", q=query, maxResults=self._max_results)
                    .execute()
                )
                messages = results.get("messages", [])
            except Exception as exc:
                log.warning("gmail.search_failed", query=query, error=str(exc))
                continue

            for msg_stub in messages:
                msg_id = msg_stub["id"]
                try:
                    message = (
                        service.users().messages().get(userId="me", id=msg_id).execute()
                    )
                    sender_email = _extract_sender(message)
                    pdf_passwords = _passwords_for_sender(sender_email)
                    attachments = self._extract_pdf_attachments(service, msg_id, message)
                    for pdf_bytes, filename in attachments:
                        account_id = self._account_id_map.get(
                            doc_type, uuid.UUID(int=0)  # Placeholder if not mapped
                        )
                        documents.append(
                            FetchedDocument(
                                raw_bytes=pdf_bytes,
                                doc_type=doc_type,
                                source=IngestionSource.GMAIL,
                                account_id=account_id,
                                suggested_filename=filename,
                                metadata={
                                    "gmail_message_id": msg_id,
                                    "sender": sender_email,
                                },
                                pdf_passwords=pdf_passwords,
                            )
                        )
                except Exception as exc:
                    log.warning("gmail.message_fetch_failed", msg_id=msg_id, error=str(exc))
                    continue

        log.info("gmail.fetch_complete", owner_id=str(owner_id), documents=len(documents))
        return documents

    def _extract_pdf_attachments(
        self, service, message_id: str, message: dict
    ) -> list[tuple[bytes, str]]:
        """Return list of (pdf_bytes, filename) for all PDF attachments in the message."""
        results = []
        parts = message.get("payload", {}).get("parts", [])

        for part in parts:
            filename = part.get("filename", "")
            mime_type = part.get("mimeType", "")

            if mime_type != "application/pdf" and not filename.lower().endswith(".pdf"):
                continue

            body = part.get("body", {})
            attachment_id = body.get("attachmentId")

            if attachment_id:
                attachment = (
                    service.users()
                    .messages()
                    .attachments()
                    .get(userId="me", messageId=message_id, id=attachment_id)
                    .execute()
                )
                data = attachment.get("data", "")
            else:
                data = body.get("data", "")

            if data:
                pdf_bytes = base64.urlsafe_b64decode(data + "==")
                results.append((pdf_bytes, filename or f"attachment_{message_id}.pdf"))

        return results
