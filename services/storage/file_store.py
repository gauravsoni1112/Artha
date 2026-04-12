"""
FileStore — encrypted local blob storage for PDF documents.

All PDFs are encrypted at rest using Fernet (AES-128-CBC + HMAC-SHA256).
The encryption key is read from FILE_STORE_KEY env var (base64 Fernet key).

Storage layout:
  {FILE_STORE_PATH}/{owner_id}/{YYYY-MM}/{file_hash}.pdf.enc

To generate a key:
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

import os
import uuid
from datetime import date
from pathlib import Path

import structlog
from cryptography.fernet import Fernet, InvalidToken

log = structlog.get_logger(__name__)

_DEFAULT_STORE_PATH = os.getenv("FILE_STORE_PATH", "/tmp/artha/documents")
_FERNET_KEY = os.getenv("FILE_STORE_KEY", "")


def _get_fernet() -> Fernet:
    key = _FERNET_KEY
    if not key:
        # Generate a temporary key for development (not persisted across restarts)
        import warnings
        warnings.warn(
            "FILE_STORE_KEY is not set. Using a temporary in-memory key. "
            "PDFs encrypted with this key will not be recoverable after restart.",
            RuntimeWarning,
            stacklevel=3,
        )
        key = Fernet.generate_key().decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


class FileStore:
    """
    Encrypts and stores PDF bytes on the local filesystem.

    Args:
        base_path: Root directory for all stored files
    """

    def __init__(self, base_path: str | None = None) -> None:
        self._base_path = Path(base_path or _DEFAULT_STORE_PATH)
        self._fernet = _get_fernet()

    async def save(
        self,
        raw_bytes: bytes,
        owner_id: uuid.UUID,
        file_hash: str,
        filename: str = "",
    ) -> str:
        """
        Encrypt and save raw_bytes to disk.

        Returns the absolute file path (stored in documents.file_path).
        """
        today = date.today()
        dir_path = self._base_path / str(owner_id) / today.strftime("%Y-%m")
        dir_path.mkdir(parents=True, exist_ok=True)

        encrypted = self._fernet.encrypt(raw_bytes)
        file_path = dir_path / f"{file_hash}.pdf.enc"
        file_path.write_bytes(encrypted)

        log.info(
            "file_store.saved",
            path=str(file_path),
            original_size=len(raw_bytes),
            encrypted_size=len(encrypted),
        )
        return str(file_path)

    async def read(self, file_path: str) -> bytes:
        """
        Read and decrypt a previously stored file.

        Raises:
            FileNotFoundError: if the file does not exist
            InvalidToken: if decryption fails (wrong key or corrupted file)
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Stored document not found: {file_path}")

        encrypted = path.read_bytes()
        try:
            return self._fernet.decrypt(encrypted)
        except InvalidToken as exc:
            raise InvalidToken(
                f"Cannot decrypt '{file_path}'. "
                "Check that FILE_STORE_KEY matches the key used when the file was stored."
            ) from exc

    async def delete(self, file_path: str) -> None:
        """Delete a stored file (e.g. when a quarantine record is purged)."""
        path = Path(file_path)
        if path.exists():
            path.unlink()
            log.info("file_store.deleted", path=file_path)
