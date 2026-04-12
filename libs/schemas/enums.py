from enum import StrEnum


class AccountType(StrEnum):
    SAVINGS = "SAVINGS"
    CHECKING = "CHECKING"
    CREDIT_CARD = "CREDIT_CARD"
    DEMAT = "DEMAT"
    MF_FOLIO = "MF_FOLIO"
    PPF = "PPF"
    NPS = "NPS"
    FD = "FD"
    OTHER = "OTHER"


class AssetClass(StrEnum):
    EQUITY = "EQUITY"
    MUTUAL_FUND = "MUTUAL_FUND"
    INSURANCE = "INSURANCE"
    REAL_ESTATE = "REAL_ESTATE"
    GOLD = "GOLD"
    FD = "FD"
    PPF = "PPF"
    NPS = "NPS"
    OTHER = "OTHER"


class IngestionSource(StrEnum):
    GMAIL = "GMAIL"
    MANUAL = "MANUAL"
    ZERODHA_API = "ZERODHA_API"


class DocumentType(StrEnum):
    BANK_STATEMENT = "BANK_STATEMENT"
    CC_STATEMENT = "CC_STATEMENT"
    MF_CAS = "MF_CAS"
    INSURANCE = "INSURANCE"
    TAX = "TAX"
    OTHER = "OTHER"


class ParseStatus(StrEnum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class IngestionRunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class TriggerType(StrEnum):
    SCHEDULED = "SCHEDULED"
    ADHOC = "ADHOC"


class TransactionType(StrEnum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


class TransactionCategory(StrEnum):
    SALARY = "SALARY"
    RENT = "RENT"
    GROCERIES = "GROCERIES"
    UTILITIES = "UTILITIES"
    TRANSPORT = "TRANSPORT"
    DINING = "DINING"
    ENTERTAINMENT = "ENTERTAINMENT"
    HEALTHCARE = "HEALTHCARE"
    EDUCATION = "EDUCATION"
    INVESTMENT = "INVESTMENT"
    INSURANCE = "INSURANCE"
    TRANSFER = "TRANSFER"
    EMI = "EMI"
    TAX = "TAX"
    INTEREST = "INTEREST"
    DIVIDEND = "DIVIDEND"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class QuarantineStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


class ValidationStage(StrEnum):
    SCHEMA = "SCHEMA"
    RANGE = "RANGE"
    ANOMALY = "ANOMALY"
    LOCALE = "LOCALE"
