"""
ParserFactory — maps DocumentType to the correct BaseParser subclass.
"""

from libs.schemas.enums import DocumentType
from services.ingestion.parsers.base import BaseParser
from services.ingestion.parsers.bank_statement import BankStatementParser
from services.ingestion.parsers.credit_card import CreditCardParser
from services.ingestion.parsers.cas_statement import CASStatementParser
from services.ingestion.parsers.manual_parser import ManualParser

_REGISTRY: dict[str, BaseParser] = {
    DocumentType.BANK_STATEMENT: BankStatementParser(),
    DocumentType.CC_STATEMENT: CreditCardParser(),
    DocumentType.MF_CAS: CASStatementParser(),
    DocumentType.INSURANCE: ManualParser(),
    DocumentType.TAX: ManualParser(),
    DocumentType.OTHER: ManualParser(),
}


def for_type(doc_type: str) -> BaseParser:
    """
    Return the parser instance for the given DocumentType.

    Raises:
        KeyError: if doc_type is not registered.
    """
    parser = _REGISTRY.get(doc_type)
    if parser is None:
        raise KeyError(f"No parser registered for DocumentType '{doc_type}'")
    return parser
