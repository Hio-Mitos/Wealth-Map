"""
WealthMap – Database Models
All SQLAlchemy ORM models for local SQLite storage.
"""

import os
import json
import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float,
    DateTime, Boolean, ForeignKey, Enum as SAEnum, LargeBinary
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.ext.hybrid import hybrid_property
import enum

Base = declarative_base()

# ─── Enums ────────────────────────────────────────────────────────────────────

class AccountType(enum.Enum):
    BANK        = "Bank Account"
    WALLET      = "Physical Wallet"
    PORTFOLIO   = "Investment Portfolio"
    CRYPTO      = "Crypto Wallet"
    SAVINGS     = "Savings Account"
    CASH        = "Cash Envelope"
    CREDIT_CARD = "Credit Card"

class TransactionType(enum.Enum):
    INCOME            = "Income"
    EXPENSE           = "Expense"
    TRANSFER          = "Transfer"
    EXCHANGE          = "Currency Exchange"
    INVESTMENT        = "Investment"
    DIVIDEND          = "Dividend"
    LOAN_IN           = "Loan Received"
    LOAN_OUT          = "Loan Given"
    REFUND            = "Refund"
    INTEREST_EARNED   = "Interest Earned"
    INTEREST_CHARGED  = "Interest Charged"
    FEE               = "Bank / Service Fee"
    TAX               = "Tax Payment"
    WITHDRAWAL        = "Cash Withdrawal"
    DEPOSIT           = "Cash Deposit"
    GIFT_RECEIVED     = "Gift Received"
    GIFT_GIVEN        = "Gift Given"
    SUBSCRIPTION      = "Subscription Payment"
    RENT_INCOME       = "Rent Income"
    SALARY            = "Salary / Payroll"
    REIMBURSEMENT     = "Reimbursement"
    DONATION          = "Donation / Charity"
    INSURANCE_PAYOUT  = "Insurance Payout"
    INSURANCE_PREMIUM = "Insurance Premium"
    ADJUSTMENT        = "Balance Adjustment"
    OTHER             = "Other"
    CUSTOM_CREDIT     = "Custom Income"
    CUSTOM_DEBIT      = "Custom Expense"

# Transaction types that increase an account's balance
CREDIT_TRANSACTION_TYPES = {
    TransactionType.INCOME, TransactionType.DIVIDEND, TransactionType.LOAN_IN,
    TransactionType.REFUND, TransactionType.INTEREST_EARNED, TransactionType.DEPOSIT,
    TransactionType.GIFT_RECEIVED, TransactionType.RENT_INCOME, TransactionType.SALARY,
    TransactionType.REIMBURSEMENT, TransactionType.INSURANCE_PAYOUT,
    TransactionType.CUSTOM_CREDIT,
}

# Transaction types that decrease an account's balance
DEBIT_TRANSACTION_TYPES = {
    TransactionType.EXPENSE, TransactionType.LOAN_OUT, TransactionType.INTEREST_CHARGED,
    TransactionType.FEE, TransactionType.TAX, TransactionType.WITHDRAWAL,
    TransactionType.GIFT_GIVEN, TransactionType.SUBSCRIPTION, TransactionType.DONATION,
    TransactionType.INSURANCE_PREMIUM, TransactionType.INVESTMENT, TransactionType.OTHER,
    TransactionType.CUSTOM_DEBIT,
}
# TRANSFER and EXCHANGE are handled with their own logic. ADJUSTMENT allows a
# signed amount (positive = corrects balance up, negative = corrects it down)
# and is added to the balance as-is.

class TransactionStatus(enum.Enum):
    PENDING     = "Pending"
    CLEARED     = "Cleared"
    RECONCILED  = "Reconciled"
    CANCELLED   = "Cancelled"

class AssetType(enum.Enum):
    STOCK       = "Stock"
    ETF         = "ETF"
    BOND        = "Bond"
    MUTUAL_FUND = "Mutual Fund"
    CRYPTO      = "Cryptocurrency"
    COMMODITY   = "Commodity"
    REAL_ESTATE = "Real Estate"
    OTHER       = "Other"

class OpportunityCategory(enum.Enum):
    CREDIT_CARD = "Credit Card"
    LOAN        = "Loan"
    MORTGAGE    = "Mortgage"
    INVESTMENT  = "Investment"
    JOB_INCOME  = "Job / Income Stream"
    BUSINESS    = "Business Venture"
    INSURANCE   = "Insurance Policy"
    ASSET       = "Asset Purchase"
    OTHER       = "Other"

class OpportunityDirection(enum.Enum):
    ASSET     = "Potential Asset"       # something that increases what you own
    LIABILITY = "Potential Liability"   # something that increases what you owe

class OpportunityStatus(enum.Enum):
    CONSIDERING = "Considering"
    RESEARCHING = "Researching"
    APPLIED     = "Applied"
    PENDING     = "Pending Decision"
    APPROVED    = "Approved"
    ACTIVE      = "Active"
    REJECTED    = "Rejected"
    DECLINED    = "Declined by Me"
    COMPLETED   = "Completed"

# ─── Core Models ──────────────────────────────────────────────────────────────

class Currency(Base):
    __tablename__ = "currencies"

    id           = Column(Integer, primary_key=True)
    code         = Column(String(10), unique=True, nullable=False)   # USD, EUR, GBP…
    name         = Column(String(100), nullable=False)               # official name
    symbol       = Column(String(10), default="")
    country      = Column(String(150), default="")                   # issuing country/region
    common_name  = Column(String(100), default="")                   # commonly-known nickname
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    exchange_rates_base   = relationship("ExchangeRate", foreign_keys="ExchangeRate.base_currency_id", back_populates="base_currency")
    exchange_rates_target = relationship("ExchangeRate", foreign_keys="ExchangeRate.target_currency_id", back_populates="target_currency")

    def __repr__(self):
        return f"<Currency {self.code}>"


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    id                 = Column(Integer, primary_key=True)
    base_currency_id   = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    target_currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    rate               = Column(Float, nullable=False)
    source             = Column(String(50), default="manual")   # 'api' | 'manual'
    fetched_at         = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    base_currency   = relationship("Currency", foreign_keys=[base_currency_id],   back_populates="exchange_rates_base")
    target_currency = relationship("Currency", foreign_keys=[target_currency_id], back_populates="exchange_rates_target")


class Account(Base):
    __tablename__ = "accounts"

    id              = Column(Integer, primary_key=True)
    name            = Column(String(200), nullable=False)
    account_type    = Column(SAEnum(AccountType), nullable=False)
    currency_id     = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    institution     = Column(String(200), default="")      # bank / broker / card issuer
    account_number  = Column(String(100), default="")      # last 4 digits or masked
    description     = Column(Text, default="")
    is_active       = Column(Boolean, default=True)
    color           = Column(String(20), default="#4A90D9")   # UI color tag
    icon            = Column(String(50), default="bank")
    balance_override= Column(Float, nullable=True)             # manual balance lock
    department_id   = Column(Integer, ForeignKey("departments.id"), nullable=True)

    # Credit-card-specific fields (nullable for other account types)
    credit_limit     = Column(Float, nullable=True)
    statement_day    = Column(Integer, nullable=True)   # day of month statement closes (1-31)
    payment_due_day  = Column(Integer, nullable=True)   # day of month payment is due (1-31)
    interest_rate    = Column(Float, nullable=True)     # APR %

    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))

    currency     = relationship("Currency")
    department   = relationship("Department")
    transactions = relationship("Transaction", back_populates="account",
                                foreign_keys="Transaction.account_id", cascade="all, delete-orphan")
    assets       = relationship("PortfolioAsset", back_populates="account",
                                cascade="all, delete-orphan")
    attachments  = relationship("Attachment", back_populates="account",
                                cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Account {self.name} ({self.account_type.value})>"


class Transaction(Base):
    __tablename__ = "transactions"

    id                    = Column(Integer, primary_key=True)
    account_id            = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    linked_account_id     = Column(Integer, ForeignKey("accounts.id"), nullable=True)  # for transfers
    transfer_group_id     = Column(String(40), nullable=True)  # links both legs of a transfer
    transaction_type      = Column(SAEnum(TransactionType), nullable=False)
    custom_type_label     = Column(String(100), nullable=True)   # display name for custom types
    department_id         = Column(Integer, ForeignKey("departments.id"), nullable=True)
    # For cross-profile transfers: the "other side" lives in a different
    # profile's database, so it can't be a real FK. linked_profile_id holds
    # the other profile's id, and linked_account_label a human-readable
    # "ProfileName: AccountName" string for display.
    linked_profile_id     = Column(String(40), nullable=True)
    linked_account_label  = Column(String(200), nullable=True)
    status                = Column(SAEnum(TransactionStatus), default=TransactionStatus.CLEARED)
    amount                = Column(Float, nullable=False)
    currency_id           = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    exchange_rate         = Column(Float, nullable=True)    # rate used at transaction time
    base_amount           = Column(Float, nullable=True)    # amount converted to base currency
    description           = Column(Text, default="")
    category              = Column(String(100), default="Uncategorized")
    tags                  = Column(Text, default="[]")      # JSON list of strings
    payee                 = Column(String(200), default="")
    reference             = Column(String(200), default="")  # bank ref / cheque no
    transaction_date      = Column(DateTime, nullable=False)
    value_date            = Column(DateTime, nullable=True)
    is_recurring          = Column(Boolean, default=False)
    notes                 = Column(Text, default="")

    # Fees & taxes attached to this transaction
    fee_amount            = Column(Float, default=0.0)
    fee_currency_id       = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    fee_description       = Column(String(200), default="")
    tax_amount            = Column(Float, default=0.0)
    tax_currency_id       = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    tax_description       = Column(String(200), default="")

    created_at            = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at            = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                                  onupdate=lambda: datetime.now(timezone.utc))

    account        = relationship("Account", foreign_keys=[account_id], back_populates="transactions")
    linked_account = relationship("Account", foreign_keys=[linked_account_id])
    department     = relationship("Department")
    currency       = relationship("Currency", foreign_keys=[currency_id])
    fee_currency   = relationship("Currency", foreign_keys=[fee_currency_id])
    tax_currency   = relationship("Currency", foreign_keys=[tax_currency_id])
    attachments    = relationship("Attachment", back_populates="transaction",
                                  cascade="all, delete-orphan")
    charges        = relationship("TransactionCharge", back_populates="transaction",
                                  cascade="all, delete-orphan")

    @property
    def tag_list(self):
        try:
            return json.loads(self.tags or "[]")
        except Exception:
            return []

    @tag_list.setter
    def tag_list(self, value):
        self.tags = json.dumps(value)

    @property
    def total_fees_taxes(self):
        total = (self.fee_amount or 0.0) + (self.tax_amount or 0.0)
        total += sum((c.amount or 0.0) for c in self.charges)
        return total

    @property
    def display_type(self) -> str:
        """The label to show in the UI: a custom type's name if set, else the enum's value."""
        return self.custom_type_label or self.transaction_type.value

    @property
    def counterparty_label(self) -> Optional[str]:
        """The name of the 'other side' of a transfer/dual-leg transaction,
        whether it's a local account or one in a linked profile."""
        if self.linked_account:
            return self.linked_account.name
        return self.linked_account_label

    def __repr__(self):
        return f"<Transaction {self.transaction_type.value} {self.amount}>"


class TransactionCharge(Base):
    """
    An additional fee or tax line item on a transaction. A transaction can
    have any number of these (in addition to the single primary fee/tax
    fields on Transaction itself, kept for backwards compatibility).
    """
    __tablename__ = "transaction_charges"

    id             = Column(Integer, primary_key=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    kind           = Column(String(10), default="fee")   # 'fee' | 'tax'
    amount         = Column(Float, nullable=False, default=0.0)
    currency_id    = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    description    = Column(String(200), default="")
    created_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    transaction = relationship("Transaction", back_populates="charges")
    currency    = relationship("Currency")

    def __repr__(self):
        return f"<TransactionCharge {self.kind} {self.amount}>"


class PortfolioAsset(Base):
    __tablename__ = "portfolio_assets"

    id              = Column(Integer, primary_key=True)
    account_id      = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    asset_type      = Column(SAEnum(AssetType), nullable=False)
    ticker          = Column(String(30), default="")        # market symbol, e.g. AAPL, BTC-USD, GC=F
    name            = Column(String(200), nullable=False)
    quantity        = Column(Float, nullable=False, default=0.0)
    average_cost    = Column(Float, nullable=False, default=0.0)   # cost per unit
    currency_id     = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    current_price   = Column(Float, nullable=True)
    last_price_update = Column(DateTime, nullable=True)
    price_source    = Column(String(30), default="manual")   # 'manual' | 'market'
    purchase_date   = Column(DateTime, nullable=True)   # when this asset was first acquired
    market_meta     = Column(Text, default="")    # JSON: day change, market cap, 52w range, etc.
    valuation_factors = Column(Text, default="")  # free-form factors that drive value (real estate/other)
    notes           = Column(Text, default="")
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))

    account  = relationship("Account", back_populates="assets")
    currency = relationship("Currency")
    trades   = relationship("AssetTrade", back_populates="asset",
                            cascade="all, delete-orphan")
    price_history = relationship("AssetPriceSnapshot", back_populates="asset",
                                 cascade="all, delete-orphan",
                                 order_by="AssetPriceSnapshot.recorded_at")
    attachments = relationship("Attachment", back_populates="asset",
                               cascade="all, delete-orphan")

    @property
    def market_meta_dict(self):
        try:
            return json.loads(self.market_meta or "{}")
        except Exception:
            return {}

    @market_meta_dict.setter
    def market_meta_dict(self, value):
        self.market_meta = json.dumps(value)

    @property
    def market_value(self):
        if self.current_price is not None:
            return self.quantity * self.current_price
        return self.quantity * self.average_cost

    @property
    def cost_basis(self):
        return self.quantity * self.average_cost

    @property
    def unrealized_pnl(self):
        if self.current_price is not None:
            return (self.current_price - self.average_cost) * self.quantity
        return 0.0

    @property
    def pnl_pct(self):
        if self.average_cost > 0 and self.current_price is not None:
            return ((self.current_price - self.average_cost) / self.average_cost) * 100
        return 0.0

    def __repr__(self):
        return f"<Asset {self.ticker or self.name} x{self.quantity}>"


class AssetTrade(Base):
    __tablename__ = "asset_trades"

    id           = Column(Integer, primary_key=True)
    asset_id     = Column(Integer, ForeignKey("portfolio_assets.id"), nullable=False)
    trade_type   = Column(String(10), nullable=False)    # BUY | SELL | DIVIDEND
    quantity     = Column(Float, nullable=False)
    price        = Column(Float, nullable=False)
    fees         = Column(Float, default=0.0)
    taxes        = Column(Float, default=0.0)
    trade_date   = Column(DateTime, nullable=False)
    notes        = Column(Text, default="")
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    asset       = relationship("PortfolioAsset", back_populates="trades")
    attachments = relationship("Attachment", back_populates="trade",
                               cascade="all, delete-orphan")


class AssetPriceSnapshot(Base):
    """
    A point-in-time price (+ market metadata) for a portfolio asset,
    recorded every time prices are refreshed. Lets the user analyse how an
    asset's price and key stats have moved over time.
    """
    __tablename__ = "asset_price_snapshots"

    id              = Column(Integer, primary_key=True)
    asset_id        = Column(Integer, ForeignKey("portfolio_assets.id"), nullable=False)
    price           = Column(Float, nullable=False)
    currency_code   = Column(String(10), default="")
    day_change_pct  = Column(Float, nullable=True)
    day_change_abs  = Column(Float, nullable=True)
    previous_close  = Column(Float, nullable=True)
    market_cap      = Column(Float, nullable=True)
    week52_high     = Column(Float, nullable=True)
    week52_low      = Column(Float, nullable=True)
    source          = Column(String(30), default="market")
    recorded_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    asset = relationship("PortfolioAsset", back_populates="price_history")

    def __repr__(self):
        return f"<AssetPriceSnapshot asset={self.asset_id} price={self.price}>"


class PersonalLoan(Base):
    """Inter-personal loans — money owed to/from people."""
    __tablename__ = "personal_loans"

    id              = Column(Integer, primary_key=True)
    contact_name    = Column(String(200), nullable=False)
    contact_info    = Column(String(300), default="")
    direction       = Column(String(10), nullable=False)   # 'owed_to_me' | 'i_owe'
    principal       = Column(Float, nullable=False)
    currency_id     = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    amount_repaid   = Column(Float, default=0.0)
    fee_amount      = Column(Float, default=0.0)           # e.g. transfer/processing fees
    fee_currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    fee_description = Column(String(200), default="")
    description     = Column(Text, default="")
    due_date        = Column(DateTime, nullable=True)
    is_settled      = Column(Boolean, default=False)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    settled_at      = Column(DateTime, nullable=True)

    currency     = relationship("Currency", foreign_keys=[currency_id])
    fee_currency = relationship("Currency", foreign_keys=[fee_currency_id])
    attachments  = relationship("Attachment", back_populates="loan",
                                cascade="all, delete-orphan")
    repayments   = relationship("LoanRepayment", back_populates="loan",
                                cascade="all, delete-orphan")

    @property
    def outstanding(self):
        return self.principal - self.amount_repaid


class LoanRepayment(Base):
    __tablename__ = "loan_repayments"

    id           = Column(Integer, primary_key=True)
    loan_id      = Column(Integer, ForeignKey("personal_loans.id"), nullable=False)
    amount       = Column(Float, nullable=False)
    fee_amount   = Column(Float, default=0.0)
    repaid_on    = Column(DateTime, nullable=False)
    notes        = Column(Text, default="")
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    loan        = relationship("PersonalLoan", back_populates="repayments")
    attachments = relationship("Attachment", back_populates="repayment",
                               cascade="all, delete-orphan")


class Receipt(Base):
    __tablename__ = "receipts"

    id               = Column(Integer, primary_key=True)
    title            = Column(String(300), nullable=False)
    merchant         = Column(String(200), default="")
    amount           = Column(Float, nullable=True)
    currency_id      = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    receipt_date     = Column(DateTime, nullable=True)
    category         = Column(String(100), default="")
    transaction_id   = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    notes            = Column(Text, default="")
    created_at       = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    currency    = relationship("Currency")
    transaction = relationship("Transaction")
    attachments = relationship("Attachment", back_populates="receipt",
                               cascade="all, delete-orphan")


class Opportunity(Base):
    """
    Tracks 'attempts' to gain (or take on) money: credit card applications,
    loan/mortgage applications, investment opportunities, new income streams,
    business ventures, etc. Each can carry supporting files (applications,
    offers, contracts, approval letters).
    """
    __tablename__ = "opportunities"

    id              = Column(Integer, primary_key=True)
    title           = Column(String(200), nullable=False)
    category        = Column(SAEnum(OpportunityCategory), nullable=False)
    direction       = Column(SAEnum(OpportunityDirection), nullable=False)
    status          = Column(SAEnum(OpportunityStatus), default=OpportunityStatus.CONSIDERING)
    institution     = Column(String(200), default="")        # bank, lender, broker, employer…
    estimated_value = Column(Float, nullable=True)            # credit limit / loan amount / investment size
    currency_id     = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    interest_rate   = Column(Float, nullable=True)            # APR / expected return %
    applied_date    = Column(DateTime, nullable=True)
    decision_date   = Column(DateTime, nullable=True)
    description     = Column(Text, default="")
    notes           = Column(Text, default="")
    linked_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)  # set once active
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))

    currency       = relationship("Currency")
    linked_account = relationship("Account")
    attachments    = relationship("Attachment", back_populates="opportunity",
                                  cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Opportunity {self.title} ({self.status.value})>"


class Attachment(Base):
    """Universal file attachment — links to any entity."""
    __tablename__ = "attachments"

    id               = Column(Integer, primary_key=True)
    # FK to owning entity (only one will be set)
    account_id       = Column(Integer, ForeignKey("accounts.id"),       nullable=True)
    transaction_id   = Column(Integer, ForeignKey("transactions.id"),   nullable=True)
    trade_id         = Column(Integer, ForeignKey("asset_trades.id"),   nullable=True)
    loan_id          = Column(Integer, ForeignKey("personal_loans.id"), nullable=True)
    repayment_id     = Column(Integer, ForeignKey("loan_repayments.id"),nullable=True)
    receipt_id       = Column(Integer, ForeignKey("receipts.id"),       nullable=True)
    opportunity_id   = Column(Integer, ForeignKey("opportunities.id"),  nullable=True)
    asset_id         = Column(Integer, ForeignKey("portfolio_assets.id"), nullable=True)

    original_filename= Column(String(500), nullable=False)
    stored_filename  = Column(String(500), nullable=False)   # UUID-based on disk
    file_path        = Column(String(1000), nullable=False)  # relative to attachments dir
    mime_type        = Column(String(100), default="application/octet-stream")
    file_size        = Column(Integer, default=0)            # bytes
    checksum         = Column(String(64), default="")        # SHA-256
    description      = Column(Text, default="")
    created_at       = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    account     = relationship("Account",        back_populates="attachments")
    transaction = relationship("Transaction",    back_populates="attachments")
    trade       = relationship("AssetTrade",     back_populates="attachments")
    loan        = relationship("PersonalLoan",   back_populates="attachments")
    repayment   = relationship("LoanRepayment",  back_populates="attachments")
    receipt     = relationship("Receipt",        back_populates="attachments")
    opportunity = relationship("Opportunity",    back_populates="attachments")
    asset       = relationship("PortfolioAsset", back_populates="attachments")


class AppSettings(Base):
    __tablename__ = "app_settings"

    id           = Column(Integer, primary_key=True)
    key          = Column(String(200), unique=True, nullable=False)
    value        = Column(Text, default="")
    updated_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))


class Department(Base):
    """
    A cost center / business unit. Primarily used by Business profiles to
    tag accounts and transactions for department-level P&L, but available
    in any profile.
    """
    __tablename__ = "departments"

    id          = Column(Integer, primary_key=True)
    name        = Column(String(100), nullable=False)
    color       = Column(String(20), default="#4A90D9")
    description = Column(Text, default="")
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Department {self.name}>"


class CustomCategory(Base):
    """User-defined transaction category, in addition to the built-in list."""
    __tablename__ = "custom_categories"

    id         = Column(Integer, primary_key=True)
    name       = Column(String(100), unique=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CustomTransactionType(Base):
    """
    User-defined transaction type. Backed by a generic credit/debit/signed
    bucket on the Transaction row (CUSTOM_CREDIT / CUSTOM_DEBIT /
    ADJUSTMENT) so balance & report logic doesn't need to know about it,
    while `Transaction.custom_type_label` carries the user-chosen name.
    """
    __tablename__ = "custom_transaction_types"

    id         = Column(Integer, primary_key=True)
    name       = Column(String(100), unique=True, nullable=False)
    direction  = Column(String(10), nullable=False, default="debit")  # 'credit'|'debit'|'signed'
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ─── Engine / Session factory ─────────────────────────────────────────────────

# Columns introduced after the initial release of each table. For existing
# SQLite databases, Base.metadata.create_all() only creates *new* tables —
# it does not add new columns to tables that already exist. We patch those
# in with ALTER TABLE ADD COLUMN, which SQLite supports for simple column
# additions (no constraints/foreign keys in the ALTER itself).
_MIGRATIONS = {
    "currencies": [
        ("country",      "VARCHAR(150) DEFAULT ''"),
        ("common_name",  "VARCHAR(100) DEFAULT ''"),
    ],
    "accounts": [
        ("credit_limit",     "FLOAT"),
        ("statement_day",    "INTEGER"),
        ("payment_due_day",  "INTEGER"),
        ("interest_rate",    "FLOAT"),
        ("department_id",    "INTEGER"),
    ],
    "transactions": [
        ("transfer_group_id", "VARCHAR(40)"),
        ("fee_amount",        "FLOAT DEFAULT 0.0"),
        ("fee_currency_id",   "INTEGER"),
        ("fee_description",   "VARCHAR(200) DEFAULT ''"),
        ("tax_amount",        "FLOAT DEFAULT 0.0"),
        ("tax_currency_id",   "INTEGER"),
        ("tax_description",   "VARCHAR(200) DEFAULT ''"),
        ("custom_type_label", "VARCHAR(100)"),
        ("department_id",     "INTEGER"),
        ("linked_profile_id", "VARCHAR(40)"),
        ("linked_account_label", "VARCHAR(200)"),
    ],
    "asset_trades": [
        ("taxes", "FLOAT DEFAULT 0.0"),
    ],
    "personal_loans": [
        ("fee_amount",      "FLOAT DEFAULT 0.0"),
        ("fee_currency_id", "INTEGER"),
        ("fee_description", "VARCHAR(200) DEFAULT ''"),
    ],
    "loan_repayments": [
        ("fee_amount", "FLOAT DEFAULT 0.0"),
    ],
    "attachments": [
        ("opportunity_id", "INTEGER"),
        ("asset_id",       "INTEGER"),
    ],
    "portfolio_assets": [
        ("price_source",      "VARCHAR(30) DEFAULT 'manual'"),
        ("market_meta",       "TEXT DEFAULT ''"),
        ("valuation_factors", "TEXT DEFAULT ''"),
        ("purchase_date",     "DATETIME"),
    ],
}


def _migrate_schema(engine):
    """Add any columns introduced in later versions to existing SQLite tables."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, columns in _MIGRATIONS.items():
            if table not in existing_tables:
                continue  # brand-new table — already created by create_all()
            existing_cols = {c["name"] for c in inspector.get_columns(table)}
            for col_name, col_def in columns:
                if col_name in existing_cols:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))


def init_db(db_path: str):
    """Create all tables, migrate existing ones, and return (engine, SessionLocal)."""
    engine = create_engine(f"sqlite:///{db_path}", echo=False,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    _migrate_schema(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, SessionLocal
