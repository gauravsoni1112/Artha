"""
Zerodha Connector — fetches holdings and trade history via Kite Connect API.

Authentication:
  Kite Connect requires an access_token that is valid for one trading day.
  Set ZERODHA_API_KEY and ZERODHA_ACCESS_TOKEN in the environment.
  Access token must be refreshed daily (Zerodha limitation).

Output:
  Returns holdings as a single FetchedDocument containing JSON bytes
  that ManualParser can deserialise into RawTransaction objects.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, timedelta

import structlog

from libs.schemas.enums import DocumentType, IngestionSource
from services.ingestion.connectors.base import ConnectorABC, FetchedDocument

log = structlog.get_logger(__name__)

# How many days of trade history to fetch per run
_DEFAULT_LOOKBACK_DAYS: int = 90


class ZerodhaConnector(ConnectorABC):
    """
    Fetches Zerodha demat account data via the Kite Connect Python SDK.

    Args:
        account_id: UUID of the Zerodha demat account in Artha's DB
        api_key: Kite Connect API key (default: ZERODHA_API_KEY env var)
        access_token: Kite Connect access token (default: ZERODHA_ACCESS_TOKEN env var)
        lookback_days: Days of trade history to fetch (default 90)
    """

    def __init__(
        self,
        account_id: uuid.UUID,
        api_key: str | None = None,
        access_token: str | None = None,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
    ) -> None:
        self._account_id = account_id
        self._api_key = api_key or os.getenv("ZERODHA_API_KEY", "")
        self._access_token = access_token or os.getenv("ZERODHA_ACCESS_TOKEN", "")
        self._lookback_days = lookback_days

    def _get_kite(self):
        """Initialise the KiteConnect client."""
        try:
            from kiteconnect import KiteConnect
        except ImportError as exc:
            raise ImportError(
                "kiteconnect is required: pip install kiteconnect"
            ) from exc

        if not self._api_key or not self._access_token:
            raise ValueError(
                "ZERODHA_API_KEY and ZERODHA_ACCESS_TOKEN must be set. "
                "Note: access_token expires daily — refresh via the Kite login flow."
            )

        kite = KiteConnect(api_key=self._api_key)
        kite.set_access_token(self._access_token)
        return kite

    async def fetch(self, owner_id: uuid.UUID) -> list[FetchedDocument]:
        """
        Fetch equity holdings + recent trades from Zerodha.

        Returns two FetchedDocument objects:
          1. Holdings (positions as of today)
          2. Trade history (last N days)
        """
        try:
            kite = self._get_kite()
        except Exception as exc:
            log.error("zerodha.auth_failed", error=str(exc))
            return []

        documents: list[FetchedDocument] = []

        # ── Holdings ──────────────────────────────────────────────
        try:
            holdings_raw = kite.holdings()
            holdings_txs = [
                {
                    "date": date.today().isoformat(),
                    "description": f"Holding: {h['tradingsymbol']} ({h['exchange']})",
                    "amount": str(h["last_price"] * h["quantity"]),  # current market value
                    "type": "CREDIT",
                    "category": "INVESTMENT",
                    "merchant": "Zerodha",
                    "extra": {
                        "isin": h.get("isin"),
                        "quantity": h.get("quantity"),
                        "average_price": h.get("average_price"),
                        "last_price": h.get("last_price"),
                        "tradingsymbol": h.get("tradingsymbol"),
                        "exchange": h.get("exchange"),
                    },
                }
                for h in holdings_raw
            ]
            documents.append(
                FetchedDocument(
                    raw_bytes=json.dumps(holdings_txs).encode(),
                    doc_type=DocumentType.OTHER,
                    source=IngestionSource.ZERODHA_API,
                    account_id=self._account_id,
                    suggested_filename=f"zerodha_holdings_{date.today().isoformat()}.json",
                )
            )
        except Exception as exc:
            log.warning("zerodha.holdings_failed", error=str(exc))

        # ── Trade History ─────────────────────────────────────────
        try:
            trades = kite.trades()
            from_date = date.today() - timedelta(days=self._lookback_days)
            recent_trades = [
                t for t in trades
                if t.get("fill_timestamp") and
                date.fromisoformat(str(t["fill_timestamp"])[:10]) >= from_date
            ]
            trade_txs = [
                {
                    "date": str(t.get("fill_timestamp", ""))[:10],
                    "description": f"Trade: {t['tradingsymbol']} {t['transaction_type']}",
                    "amount": str(t["average_price"] * t["quantity"]),
                    "type": "DEBIT" if t["transaction_type"] == "BUY" else "CREDIT",
                    "category": "INVESTMENT",
                    "merchant": "Zerodha",
                }
                for t in recent_trades
            ]
            if trade_txs:
                documents.append(
                    FetchedDocument(
                        raw_bytes=json.dumps(trade_txs).encode(),
                        doc_type=DocumentType.OTHER,
                        source=IngestionSource.ZERODHA_API,
                        account_id=self._account_id,
                        suggested_filename=f"zerodha_trades_{date.today().isoformat()}.json",
                    )
                )
        except Exception as exc:
            log.warning("zerodha.trades_failed", error=str(exc))

        log.info("zerodha.fetch_complete", owner_id=str(owner_id), documents=len(documents))
        return documents
