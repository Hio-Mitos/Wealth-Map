"""
WealthMap – Core Services
Business logic: exchange rates, balance calculations, file I/O, seeding.
"""

import os
import uuid
import json
import shutil
import hashlib
import mimetypes
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Tuple

import requests
from sqlalchemy.orm import Session

from src.models.database import (
    Currency, ExchangeRate, Account, Transaction, PortfolioAsset,
    AssetTrade, PersonalLoan, LoanRepayment, Receipt, Attachment,
    AppSettings, AccountType, TransactionType, TransactionStatus, AssetType,
    Opportunity, OpportunityCategory, OpportunityDirection, OpportunityStatus,
    TransactionCharge, AssetPriceSnapshot,
    CREDIT_TRANSACTION_TYPES, DEBIT_TRANSACTION_TYPES,
    CustomCategory, CustomTransactionType
)

# ─── Constants ────────────────────────────────────────────────────────────────

EXCHANGE_API_URL = "https://api.exchangerate-api.com/v4/latest/{base}"   # free, no key
RATE_CACHE_MINUTES = 60

COMMON_CURRENCIES = [
    # ── Global majors ─────────────────────────────────────────────────────────
    ("USD", "US Dollar",              "$"),
    ("EUR", "Euro",                   "€"),
    ("GBP", "British Pound",          "£"),
    ("JPY", "Japanese Yen",           "¥"),
    ("CHF", "Swiss Franc",            "Fr"),
    ("CAD", "Canadian Dollar",        "CA$"),
    ("AUD", "Australian Dollar",      "A$"),
    ("NZD", "New Zealand Dollar",     "NZ$"),

    # ── Central & West Africa ─────────────────────────────────────────────────
    ("XAF", "CFA Franc BEAC (Central Africa)", "FCFA"),   # Cameroon, Gabon, Congo, Chad, CAR, Eq. Guinea
    ("XOF", "CFA Franc BCEAO (West Africa)",   "CFA"),    # Senegal, Côte d'Ivoire, Burkina Faso, Mali…
    ("XCD", "East Caribbean Dollar",            "EC$"),
    ("NGN", "Nigerian Naira",                   "₦"),
    ("GHS", "Ghanaian Cedi",                    "₵"),
    ("KES", "Kenyan Shilling",                  "KSh"),
    ("TZS", "Tanzanian Shilling",               "TSh"),
    ("UGX", "Ugandan Shilling",                 "USh"),
    ("RWF", "Rwandan Franc",                    "RF"),
    ("ETB", "Ethiopian Birr",                   "Br"),
    ("ZAR", "South African Rand",               "R"),
    ("ZMW", "Zambian Kwacha",                   "ZK"),
    ("BWP", "Botswana Pula",                    "P"),
    ("MUR", "Mauritian Rupee",                  "Rs"),
    ("MZN", "Mozambican Metical",               "MT"),
    ("AOA", "Angolan Kwanza",                   "Kz"),
    ("CDF", "Congolese Franc (DRC)",            "FC"),
    ("GNF", "Guinean Franc",                    "FG"),
    ("MGA", "Malagasy Ariary",                  "Ar"),
    ("SCR", "Seychellois Rupee",                "SR"),
    ("EGP", "Egyptian Pound",                   "£"),
    ("MAD", "Moroccan Dirham",                  "MAD"),
    ("TND", "Tunisian Dinar",                   "DT"),
    ("DZD", "Algerian Dinar",                   "DA"),
    ("LYD", "Libyan Dinar",                     "LD"),

    # ── South & Southeast Asia ────────────────────────────────────────────────
    ("PHP", "Philippine Peso",        "₱"),
    ("INR", "Indian Rupee",           "₹"),
    ("PKR", "Pakistani Rupee",        "Rs"),
    ("BDT", "Bangladeshi Taka",       "৳"),
    ("LKR", "Sri Lankan Rupee",       "Rs"),
    ("NPR", "Nepalese Rupee",         "Rs"),
    ("MMK", "Myanmar Kyat",           "K"),
    ("THB", "Thai Baht",              "฿"),
    ("VND", "Vietnamese Dong",        "₫"),
    ("IDR", "Indonesian Rupiah",      "Rp"),
    ("MYR", "Malaysian Ringgit",      "RM"),
    ("SGD", "Singapore Dollar",       "S$"),
    ("KHR", "Cambodian Riel",         "៛"),
    ("LAK", "Lao Kip",                "₭"),
    ("BND", "Brunei Dollar",          "B$"),

    # ── East Asia ─────────────────────────────────────────────────────────────
    ("CNY", "Chinese Yuan",           "¥"),
    ("HKD", "Hong Kong Dollar",       "HK$"),
    ("TWD", "Taiwan New Dollar",      "NT$"),
    ("KRW", "South Korean Won",       "₩"),
    ("MNT", "Mongolian Tugrik",       "₮"),

    # ── Middle East & Central Asia ────────────────────────────────────────────
    ("AED", "UAE Dirham",             "د.إ"),
    ("SAR", "Saudi Riyal",            "﷼"),
    ("QAR", "Qatari Riyal",           "﷼"),
    ("KWD", "Kuwaiti Dinar",          "KD"),
    ("BHD", "Bahraini Dinar",         "BD"),
    ("OMR", "Omani Rial",             "RO"),
    ("ILS", "Israeli New Shekel",     "₪"),
    ("TRY", "Turkish Lira",           "₺"),
    ("IRR", "Iranian Rial",           "﷼"),
    ("IQD", "Iraqi Dinar",            "ID"),
    ("KZT", "Kazakhstani Tenge",      "₸"),
    ("UZS", "Uzbekistani Som",        "so'm"),

    # ── Europe ────────────────────────────────────────────────────────────────
    ("SEK", "Swedish Krona",          "kr"),
    ("NOK", "Norwegian Krone",        "kr"),
    ("DKK", "Danish Krone",           "kr"),
    ("PLN", "Polish Zloty",           "zł"),
    ("CZK", "Czech Koruna",           "Kč"),
    ("HUF", "Hungarian Forint",       "Ft"),
    ("RUB", "Russian Ruble",          "₽"),
    ("RON", "Romanian Leu",           "lei"),
    ("HRK", "Croatian Kuna",          "kn"),
    ("BGN", "Bulgarian Lev",          "лв"),
    ("RSD", "Serbian Dinar",          "din"),
    ("UAH", "Ukrainian Hryvnia",      "₴"),
    ("GEL", "Georgian Lari",          "₾"),

    # ── Americas ──────────────────────────────────────────────────────────────
    ("MXN", "Mexican Peso",           "$"),
    ("BRL", "Brazilian Real",         "R$"),
    ("ARS", "Argentine Peso",         "$"),
    ("CLP", "Chilean Peso",           "$"),
    ("COP", "Colombian Peso",         "$"),
    ("PEN", "Peruvian Sol",           "S/"),
    ("BOB", "Bolivian Boliviano",     "Bs"),
    ("PYG", "Paraguayan Guaraní",     "₲"),
    ("UYU", "Uruguayan Peso",         "$U"),
    ("VES", "Venezuelan Bolívar",     "Bs.S"),
    ("GTQ", "Guatemalan Quetzal",     "Q"),
    ("HNL", "Honduran Lempira",       "L"),
    ("CRC", "Costa Rican Colón",      "₡"),
    ("DOP", "Dominican Peso",         "RD$"),
    ("JMD", "Jamaican Dollar",        "J$"),

    # ── Pacific ───────────────────────────────────────────────────────────────
    ("FJD", "Fijian Dollar",          "FJ$"),
    ("PGK", "Papua New Guinean Kina", "K"),
    ("WST", "Samoan Tala",            "T"),

    # ── Crypto ────────────────────────────────────────────────────────────────
    ("BTC", "Bitcoin",                "₿"),
    ("ETH", "Ethereum",               "Ξ"),
    ("USDT","Tether",                 "₮"),
    ("BNB", "Binance Coin",           "BNB"),
    ("XRP", "Ripple",                 "XRP"),
]

# code -> (country / issuing region, commonly-known nickname)
CURRENCY_INFO: Dict[str, Tuple[str, str]] = {
    "USD": ("United States", "Buck / Dollar"),
    "EUR": ("Eurozone (20 EU countries)", "Euro"),
    "GBP": ("United Kingdom", "Quid / Sterling"),
    "JPY": ("Japan", "Yen"),
    "CHF": ("Switzerland & Liechtenstein", "Swissie"),
    "CAD": ("Canada", "Loonie"),
    "AUD": ("Australia", "Aussie Dollar"),
    "NZD": ("New Zealand", "Kiwi Dollar"),

    "XAF": ("Cameroon, Chad, CAR, Congo, Gabon, Eq. Guinea (CEMAC)", "CFA Franc"),
    "XOF": ("Senegal, Côte d'Ivoire, Mali, Burkina Faso, Benin, Togo, Niger, Guinea-Bissau (UEMOA)", "CFA Franc"),
    "XCD": ("Eastern Caribbean (Antigua, Dominica, Grenada, St Lucia…)", "Eastern Caribbean Dollar"),
    "NGN": ("Nigeria", "Naira"),
    "GHS": ("Ghana", "Cedi"),
    "KES": ("Kenya", "Shilling"),
    "TZS": ("Tanzania", "Shilingi"),
    "UGX": ("Uganda", "Shilling"),
    "RWF": ("Rwanda", "Ifaranga"),
    "ETB": ("Ethiopia", "Birr"),
    "ZAR": ("South Africa", "Rand"),
    "ZMW": ("Zambia", "Kwacha"),
    "BWP": ("Botswana", "Pula"),
    "MUR": ("Mauritius", "Rupee"),
    "MZN": ("Mozambique", "Metical"),
    "AOA": ("Angola", "Kwanza"),
    "CDF": ("Democratic Republic of the Congo", "Congolese Franc"),
    "GNF": ("Guinea", "Franc Guinéen"),
    "MGA": ("Madagascar", "Ariary"),
    "SCR": ("Seychelles", "Rupee"),
    "EGP": ("Egypt", "Geneih"),
    "MAD": ("Morocco", "Dirham"),
    "TND": ("Tunisia", "Dinar"),
    "DZD": ("Algeria", "Dinar"),
    "LYD": ("Libya", "Dinar"),

    "PHP": ("Philippines", "Piso"),
    "INR": ("India", "Rupee"),
    "PKR": ("Pakistan", "Rupee"),
    "BDT": ("Bangladesh", "Taka"),
    "LKR": ("Sri Lanka", "Rupee"),
    "NPR": ("Nepal", "Rupee"),
    "MMK": ("Myanmar", "Kyat"),
    "THB": ("Thailand", "Baht"),
    "VND": ("Vietnam", "Dong"),
    "IDR": ("Indonesia", "Rupiah"),
    "MYR": ("Malaysia", "Ringgit"),
    "SGD": ("Singapore", "Sing Dollar"),
    "KHR": ("Cambodia", "Riel"),
    "LAK": ("Laos", "Kip"),
    "BND": ("Brunei", "Brunei Dollar"),

    "CNY": ("China", "Yuan / Renminbi"),
    "HKD": ("Hong Kong", "Hong Kong Dollar"),
    "TWD": ("Taiwan", "New Taiwan Dollar"),
    "KRW": ("South Korea", "Won"),
    "MNT": ("Mongolia", "Tugrik"),

    "AED": ("United Arab Emirates", "Dirham"),
    "SAR": ("Saudi Arabia", "Riyal"),
    "QAR": ("Qatar", "Riyal"),
    "KWD": ("Kuwait", "Dinar"),
    "BHD": ("Bahrain", "Dinar"),
    "OMR": ("Oman", "Rial"),
    "ILS": ("Israel", "Shekel"),
    "TRY": ("Turkey", "Lira"),
    "IRR": ("Iran", "Rial"),
    "IQD": ("Iraq", "Dinar"),
    "KZT": ("Kazakhstan", "Tenge"),
    "UZS": ("Uzbekistan", "Som"),

    "SEK": ("Sweden", "Krona"),
    "NOK": ("Norway", "Krone"),
    "DKK": ("Denmark", "Krone"),
    "PLN": ("Poland", "Złoty"),
    "CZK": ("Czech Republic", "Koruna"),
    "HUF": ("Hungary", "Forint"),
    "RUB": ("Russia", "Ruble"),
    "RON": ("Romania", "Leu"),
    "HRK": ("Croatia", "Kuna"),
    "BGN": ("Bulgaria", "Lev"),
    "RSD": ("Serbia", "Dinar"),
    "UAH": ("Ukraine", "Hryvnia"),
    "GEL": ("Georgia", "Lari"),

    "MXN": ("Mexico", "Peso"),
    "BRL": ("Brazil", "Real"),
    "ARS": ("Argentina", "Peso"),
    "CLP": ("Chile", "Peso"),
    "COP": ("Colombia", "Peso"),
    "PEN": ("Peru", "Sol"),
    "BOB": ("Bolivia", "Boliviano"),
    "PYG": ("Paraguay", "Guaraní"),
    "UYU": ("Uruguay", "Peso"),
    "VES": ("Venezuela", "Bolívar"),
    "GTQ": ("Guatemala", "Quetzal"),
    "HNL": ("Honduras", "Lempira"),
    "CRC": ("Costa Rica", "Colón"),
    "DOP": ("Dominican Republic", "Peso"),
    "JMD": ("Jamaica", "Jamaican Dollar"),

    "FJD": ("Fiji", "Fiji Dollar"),
    "PGK": ("Papua New Guinea", "Kina"),
    "WST": ("Samoa", "Tala"),

    "BTC": ("Global (decentralized)", "Bitcoin"),
    "ETH": ("Global (decentralized)", "Ether"),
    "USDT": ("Global (decentralized, USD-pegged)", "Tether"),
    "BNB": ("Global (Binance ecosystem)", "BNB"),
    "XRP": ("Global (decentralized)", "Ripple"),
}

TRANSACTION_CATEGORIES = [
    "Food & Dining", "Groceries", "Transport", "Housing & Rent",
    "Utilities", "Healthcare", "Entertainment", "Shopping",
    "Travel", "Education", "Investment", "Salary / Income",
    "Freelance", "Business", "Gifts", "Charity", "Insurance",
    "Taxes", "Loan Payment", "Transfer", "Exchange", "Other"
]


# ─── Settings Service ─────────────────────────────────────────────────────────

class SettingsService:
    def __init__(self, session: Session):
        self.db = session

    def get(self, key: str, default=None):
        row = self.db.query(AppSettings).filter_by(key=key).first()
        if row is None:
            return default
        try:
            return json.loads(row.value)
        except Exception:
            return row.value

    def set(self, key: str, value):
        row = self.db.query(AppSettings).filter_by(key=key).first()
        serialized = json.dumps(value) if not isinstance(value, str) else value
        if row:
            row.value = serialized
            row.updated_at = datetime.now(timezone.utc)
        else:
            self.db.add(AppSettings(key=key, value=serialized))
        self.db.commit()


# ─── Customization Service (custom categories & transaction types) ────────────

class CustomizationService:
    """
    Lets the user extend the built-in transaction categories and define their
    own transaction types (each backed by a credit/debit/signed balance
    bucket so the rest of the app's math doesn't need to know about them).
    """
    DIRECTIONS = ["credit", "debit", "signed"]
    DIRECTION_LABELS = {
        "credit": "Increases balance (like income)",
        "debit":  "Decreases balance (like an expense)",
        "signed": "Either direction (enter a +/- amount)",
    }

    def __init__(self, session: Session):
        self.db = session

    # Categories
    def get_categories(self) -> List[str]:
        custom = [c.name for c in self.db.query(CustomCategory).order_by(CustomCategory.name).all()]
        # de-dupe while preserving built-ins first, then custom (alphabetical)
        seen = set(TRANSACTION_CATEGORIES)
        extra = [c for c in custom if c not in seen]
        return list(TRANSACTION_CATEGORIES) + extra

    def add_category(self, name: str) -> CustomCategory:
        name = name.strip()
        if not name:
            raise ValueError("Category name cannot be empty")
        if name in TRANSACTION_CATEGORIES:
            raise ValueError(f"'{name}' already exists as a built-in category")
        existing = self.db.query(CustomCategory).filter_by(name=name).first()
        if existing:
            return existing
        cat = CustomCategory(name=name)
        self.db.add(cat)
        self.db.commit()
        return cat

    def remove_category(self, name: str):
        cat = self.db.query(CustomCategory).filter_by(name=name).first()
        if cat:
            self.db.delete(cat)
            self.db.commit()

    # Transaction types
    def get_custom_types(self) -> List[CustomTransactionType]:
        return (self.db.query(CustomTransactionType)
                .order_by(CustomTransactionType.name).all())

    def add_custom_type(self, name: str, direction: str = "debit") -> CustomTransactionType:
        name = name.strip()
        if not name:
            raise ValueError("Type name cannot be empty")
        if direction not in self.DIRECTIONS:
            raise ValueError(f"direction must be one of {self.DIRECTIONS}")
        if any(name == t.value for t in TransactionType):
            raise ValueError(f"'{name}' already exists as a built-in transaction type")
        existing = self.db.query(CustomTransactionType).filter_by(name=name).first()
        if existing:
            existing.direction = direction
            self.db.commit()
            return existing
        ct = CustomTransactionType(name=name, direction=direction)
        self.db.add(ct)
        self.db.commit()
        return ct

    def remove_custom_type(self, custom_type_id: int):
        ct = self.db.query(CustomTransactionType).get(custom_type_id)
        if ct:
            self.db.delete(ct)
            self.db.commit()

    def resolve_type(self, type_label: str):
        """
        Given a label from the Type combo (built-in or custom), return
        (TransactionType enum member, custom_label_or_None).
        """
        for t in TransactionType:
            if t.value == type_label:
                return t, None
        ct = self.db.query(CustomTransactionType).filter_by(name=type_label).first()
        if ct:
            bucket = {
                "credit": TransactionType.CUSTOM_CREDIT,
                "debit":  TransactionType.CUSTOM_DEBIT,
                "signed": TransactionType.ADJUSTMENT,
            }[ct.direction]
            return bucket, ct.name
        # Fallback: treat unknown labels as a generic expense
        return TransactionType.OTHER, type_label


# ─── Currency Service ─────────────────────────────────────────────────────────

class CurrencyService:
    def __init__(self, session: Session, settings: SettingsService):
        self.db = session
        self.settings = settings

    def seed_currencies(self):
        """Insert new currencies; update symbol/country/common_name if record already exists."""
        for code, name, symbol in COMMON_CURRENCIES:
            country, common_name = CURRENCY_INFO.get(code, ("", ""))
            existing = self.db.query(Currency).filter_by(code=code).first()
            if existing:
                # Update name/symbol/metadata in case they were improved
                existing.name        = name
                existing.symbol      = symbol
                existing.country     = country
                existing.common_name = common_name
            else:
                self.db.add(Currency(code=code, name=name, symbol=symbol,
                                     country=country, common_name=common_name))
        self.db.commit()

    def get_all(self) -> List[Currency]:
        return self.db.query(Currency).filter_by(is_active=True).order_by(Currency.code).all()

    def get_by_code(self, code: str) -> Optional[Currency]:
        return self.db.query(Currency).filter_by(code=code).first()

    def get_rate(self, base_code: str, target_code: str) -> Optional[float]:
        if base_code == target_code:
            return 1.0
        base = self.get_by_code(base_code)
        target = self.get_by_code(target_code)
        if not base or not target:
            return None
        row = (self.db.query(ExchangeRate)
               .filter_by(base_currency_id=base.id, target_currency_id=target.id)
               .order_by(ExchangeRate.fetched_at.desc())
               .first())
        if row:
            age = datetime.now(timezone.utc) - row.fetched_at.replace(tzinfo=timezone.utc)
            if age.total_seconds() < RATE_CACHE_MINUTES * 60:
                return row.rate
        return None

    def fetch_rates_online(self, base_code: str = "USD") -> Dict[str, float]:
        try:
            resp = requests.get(EXCHANGE_API_URL.format(base=base_code), timeout=8)
            resp.raise_for_status()
            data = resp.json()
            rates = data.get("rates", {})
            base_cur = self.get_by_code(base_code)
            if not base_cur:
                return {}
            for code, rate in rates.items():
                target_cur = self.get_by_code(code)
                if not target_cur:
                    continue
                existing = (self.db.query(ExchangeRate)
                            .filter_by(base_currency_id=base_cur.id,
                                       target_currency_id=target_cur.id)
                            .first())
                if existing:
                    existing.rate = rate
                    existing.fetched_at = datetime.now(timezone.utc)
                    existing.source = "api"
                else:
                    self.db.add(ExchangeRate(
                        base_currency_id=base_cur.id,
                        target_currency_id=target_cur.id,
                        rate=rate, source="api"
                    ))
            self.db.commit()
            self.settings.set("last_rate_fetch", datetime.now(timezone.utc).isoformat())
            return rates
        except Exception as e:
            print(f"[ExchangeRate] Fetch failed: {e}")
            return {}

    def convert(self, amount: float, from_code: str, to_code: str) -> Optional[float]:
        if from_code == to_code:
            return amount
        rate = self.get_rate(from_code, to_code)
        if rate:
            return amount * rate
        # Try via USD pivot
        r1 = self.get_rate(from_code, "USD")
        r2 = self.get_rate("USD", to_code)
        if r1 and r2:
            return amount * r1 * r2
        return None

    def set_manual_rate(self, base_code: str, target_code: str, rate: float):
        base = self.get_by_code(base_code)
        target = self.get_by_code(target_code)
        if not base or not target:
            raise ValueError(f"Unknown currency: {base_code} or {target_code}")
        existing = (self.db.query(ExchangeRate)
                    .filter_by(base_currency_id=base.id, target_currency_id=target.id)
                    .first())
        if existing:
            existing.rate = rate
            existing.fetched_at = datetime.now(timezone.utc)
            existing.source = "manual"
        else:
            self.db.add(ExchangeRate(
                base_currency_id=base.id, target_currency_id=target.id,
                rate=rate, source="manual"
            ))
        # Also set inverse
        inv = (self.db.query(ExchangeRate)
               .filter_by(base_currency_id=target.id, target_currency_id=base.id)
               .first())
        if inv:
            inv.rate = 1.0 / rate
            inv.fetched_at = datetime.now(timezone.utc)
            inv.source = "manual"
        else:
            self.db.add(ExchangeRate(
                base_currency_id=target.id, target_currency_id=base.id,
                rate=1.0 / rate, source="manual"
            ))
        self.db.commit()


# ─── Account Service ──────────────────────────────────────────────────────────

class AccountService:
    def __init__(self, session: Session, currency_svc: CurrencyService, settings: SettingsService):
        self.db = session
        self.fx = currency_svc
        self.settings = settings

    def create(self, name: str, account_type: AccountType, currency_code: str,
               institution: str = "", account_number: str = "",
               description: str = "", color: str = "#4A90D9",
               credit_limit: Optional[float] = None,
               statement_day: Optional[int] = None,
               payment_due_day: Optional[int] = None,
               interest_rate: Optional[float] = None) -> Account:
        cur = self.fx.get_by_code(currency_code)
        if not cur:
            raise ValueError(f"Currency {currency_code} not found")
        acc = Account(
            name=name, account_type=account_type,
            currency_id=cur.id, institution=institution,
            account_number=account_number, description=description,
            color=color,
            credit_limit=credit_limit, statement_day=statement_day,
            payment_due_day=payment_due_day, interest_rate=interest_rate,
        )
        self.db.add(acc)
        self.db.commit()
        self.db.refresh(acc)
        return acc

    def update(self, account: Account, **fields) -> Account:
        """
        Edit an existing account. Accepts any of: name, account_type,
        currency_code, institution, account_number, description, color,
        is_active, balance_override, credit_limit, statement_day,
        payment_due_day, interest_rate.
        """
        if "currency_code" in fields:
            code = fields.pop("currency_code")
            cur = self.fx.get_by_code(code)
            if not cur:
                raise ValueError(f"Currency {code} not found")
            account.currency_id = cur.id
        for key, value in fields.items():
            if hasattr(account, key):
                setattr(account, key, value)
        account.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(account)
        return account

    def delete(self, account: Account):
        self.db.delete(account)
        self.db.commit()

    def get_all(self, include_inactive=False) -> List[Account]:
        q = self.db.query(Account)
        if not include_inactive:
            q = q.filter_by(is_active=True)
        return q.order_by(Account.name).all()

    def get_balance(self, account: Account) -> float:
        """Compute running balance from transactions.

        Fees and taxes attached to a transaction (the primary fee/tax
        fields, plus any number of additional TransactionCharge rows) are
        always an additional outflow from *this* account, regardless of the
        transaction's type — e.g. a bank charges you a wire fee on an
        incoming transfer.
        """
        if account.balance_override is not None:
            return account.balance_override
        total = 0.0
        for tx in account.transactions:
            if tx.status == TransactionStatus.CANCELLED:
                continue
            ttype = tx.transaction_type
            if ttype in CREDIT_TRANSACTION_TYPES:
                total += tx.amount
            elif ttype in DEBIT_TRANSACTION_TYPES:
                total -= tx.amount
            elif ttype == TransactionType.TRANSFER:
                total -= tx.amount    # debit on source; credit handled on linked account
            elif ttype == TransactionType.ADJUSTMENT:
                total += tx.amount    # signed: positive corrects up, negative corrects down
            # EXCHANGE: no direct balance effect (handled via paired entries if needed)

            # Fees & taxes — same-currency assumption for the running balance
            total -= (tx.fee_amount or 0.0)
            total -= (tx.tax_amount or 0.0)
            for charge in tx.charges:
                total -= (charge.amount or 0.0)
        return total

    def credit_card_info(self, account: Account, base_code: Optional[str] = None) -> Optional[Dict]:
        """For CREDIT_CARD accounts: returns owed / available credit / limit."""
        if account.account_type != AccountType.CREDIT_CARD:
            return None
        bal = self.get_balance(account)
        owed = max(0.0, -bal)               # negative balance = amount owed
        credit = bal if bal > 0 else 0.0    # positive balance = credit/overpayment
        limit = account.credit_limit or 0.0
        available = max(0.0, limit - owed)
        return {
            "owed": owed, "credit": credit, "limit": limit,
            "available": available,
            "utilization_pct": (owed / limit * 100) if limit else 0.0,
        }

    def get_balance_in_base(self, account: Account, base_code: str) -> Optional[float]:
        bal = self.get_balance(account)
        return self.fx.convert(bal, account.currency.code, base_code)

    def net_worth_snapshot(self, base_code: str = "USD") -> Dict:
        accounts = self.get_all()
        total = 0.0
        breakdown = []
        for acc in accounts:
            bal = self.get_balance(acc)
            bal_base = self.fx.convert(bal, acc.currency.code, base_code) or 0.0
            total += bal_base
            breakdown.append({
                "id": acc.id, "name": acc.name,
                "type": acc.account_type.value,
                "balance": bal, "currency": acc.currency.code,
                "balance_base": bal_base, "base_currency": base_code,
                "color": acc.color,
            })
        return {"total": total, "base_currency": base_code, "accounts": breakdown}


# ─── Transaction Service ──────────────────────────────────────────────────────

class TransactionService:
    def __init__(self, session: Session, currency_svc: CurrencyService, settings: SettingsService):
        self.db = session
        self.fx = currency_svc
        self.settings = settings

    def add(self, account: Account, tx_type: TransactionType, amount: float,
            description: str = "", category: str = "Other",
            payee: str = "", reference: str = "",
            transaction_date: Optional[datetime] = None,
            currency_code: Optional[str] = None,
            exchange_rate: Optional[float] = None,
            linked_account: Optional[Account] = None,
            tags: Optional[List[str]] = None,
            notes: str = "", status: TransactionStatus = TransactionStatus.CLEARED,
            fee_amount: float = 0.0, fee_currency_code: Optional[str] = None,
            fee_description: str = "",
            tax_amount: float = 0.0, tax_currency_code: Optional[str] = None,
            tax_description: str = "",
            charges: Optional[List[dict]] = None,
            custom_type_label: Optional[str] = None,
            transfer_group_id_override: Optional[str] = None,
            linked_profile_id: Optional[str] = None,
            linked_account_label: Optional[str] = None,
            department_id: Optional[int] = None) -> Transaction:
        """
        charges: optional list of additional fee/tax line items, each a dict
        with keys: kind ('fee'|'tax'), amount, currency_code (optional,
        defaults to the transaction's currency), description.
        """

        base_code = self.settings.get("base_currency", "USD")
        cur_code = currency_code or account.currency.code
        cur = self.fx.get_by_code(cur_code)
        if not cur:
            raise ValueError(f"Currency {cur_code} not found")
        if transaction_date is None:
            transaction_date = datetime.now(timezone.utc)

        rate = exchange_rate
        if rate is None and cur_code != base_code:
            rate = self.fx.get_rate(cur_code, base_code)

        base_amount = amount * (rate or 1.0) if cur_code != base_code else amount

        fee_cur = self.fx.get_by_code(fee_currency_code) if fee_currency_code else cur
        tax_cur = self.fx.get_by_code(tax_currency_code) if tax_currency_code else cur

        # Any transaction type can optionally involve a second ("linked")
        # account. EXCHANGE and ADJUSTMENT are single-account by nature and
        # don't get a mirrored leg even if a linked account is set.
        DUAL_LEG_TYPES = (CREDIT_TRANSACTION_TYPES | DEBIT_TRANSACTION_TYPES |
                         {TransactionType.TRANSFER})
        transfer_group_id = None
        if linked_account and tx_type in DUAL_LEG_TYPES:
            transfer_group_id = transfer_group_id_override or uuid.uuid4().hex
        elif transfer_group_id_override and tx_type in DUAL_LEG_TYPES:
            # Cross-profile leg: the "other side" lives in a different
            # profile's database (see linked_profile_id/linked_account_label
            # below), so there's no local `linked_account` — but both legs
            # still share this transfer_group_id for display/reconciliation.
            transfer_group_id = transfer_group_id_override

        tx = Transaction(
            account_id=account.id,
            linked_account_id=linked_account.id if linked_account else None,
            transfer_group_id=transfer_group_id,
            transaction_type=tx_type,
            custom_type_label=custom_type_label,
            linked_profile_id=linked_profile_id,
            linked_account_label=linked_account_label,
            department_id=department_id,
            status=status,
            amount=amount,
            currency_id=cur.id,
            exchange_rate=rate,
            base_amount=base_amount,
            description=description,
            category=category,
            payee=payee,
            reference=reference,
            transaction_date=transaction_date,
            notes=notes,
            fee_amount=fee_amount,
            fee_currency_id=(fee_cur.id if fee_cur else None),
            fee_description=fee_description,
            tax_amount=tax_amount,
            tax_currency_id=(tax_cur.id if tax_cur else None),
            tax_description=tax_description,
        )
        if tags:
            tx.tag_list = tags
        self.db.add(tx)

        for ch in (charges or []):
            ch_amount = ch.get("amount") or 0.0
            if ch_amount == 0:
                continue
            ch_cur_code = ch.get("currency_code") or cur_code
            ch_cur = self.fx.get_by_code(ch_cur_code)
            self.db.add(TransactionCharge(
                transaction=tx,
                kind=ch.get("kind", "fee"),
                amount=ch_amount,
                currency_id=(ch_cur.id if ch_cur else None),
                description=ch.get("description", ""),
            ))

        # If this transaction involves a second account, create the mirrored
        # leg on it (handles cross-currency via fx conversion). The mirror's
        # direction depends on whether money left (debit) or arrived (credit)
        # at the primary account.
        if linked_account and transfer_group_id:
            if tx_type == TransactionType.TRANSFER or tx_type in DEBIT_TRANSACTION_TYPES:
                mirror_type, desc_prefix, mirror_category = TransactionType.INCOME, "Transfer from", "Transfer"
            else:  # CREDIT_TRANSACTION_TYPES
                mirror_type, desc_prefix, mirror_category = TransactionType.EXPENSE, "Transfer to", "Transfer"

            converted = self.fx.convert(amount, cur_code, linked_account.currency.code) or amount
            mirror = Transaction(
                account_id=linked_account.id,
                linked_account_id=account.id,
                transfer_group_id=transfer_group_id,
                transaction_type=mirror_type,
                status=status,
                amount=converted,
                currency_id=linked_account.currency_id,
                exchange_rate=exchange_rate,
                base_amount=base_amount,
                description=description or f"{desc_prefix} {account.name}",
                category=mirror_category,
                transaction_date=transaction_date,
                notes=notes,
            )
            self.db.add(mirror)

        self.db.commit()
        self.db.refresh(tx)
        return tx

    def update(self, tx: Transaction, **fields) -> Transaction:
        """
        Edit an existing transaction. Accepts field-level updates:
        description, category, payee, reference, transaction_date, notes,
        status, amount, currency_code, fee_amount, fee_currency_code,
        fee_description, tax_amount, tax_currency_code, tax_description,
        transaction_type, charges (replaces all additional fee/tax line
        items — pass a list of dicts with kind/amount/currency_code/description,
        or an empty list to clear them all).

        If `amount` or `currency_code` changes on a transfer leg, the
        linked leg's amount is recomputed via currency conversion so both
        sides stay consistent.
        """
        base_code = self.settings.get("base_currency", "USD")

        charges = fields.pop("charges", None)

        if "currency_code" in fields:
            code = fields.pop("currency_code")
            cur = self.fx.get_by_code(code)
            if not cur:
                raise ValueError(f"Currency {code} not found")
            tx.currency_id = cur.id

        if "fee_currency_code" in fields:
            code = fields.pop("fee_currency_code")
            cur = self.fx.get_by_code(code) if code else tx.currency
            tx.fee_currency_id = cur.id if cur else None

        if "tax_currency_code" in fields:
            code = fields.pop("tax_currency_code")
            cur = self.fx.get_by_code(code) if code else tx.currency
            tx.tax_currency_id = cur.id if cur else None

        for key, value in fields.items():
            if hasattr(tx, key):
                setattr(tx, key, value)

        if charges is not None:
            for old in list(tx.charges):
                self.db.delete(old)
            for ch in charges:
                ch_amount = ch.get("amount") or 0.0
                if ch_amount == 0:
                    continue
                ch_cur_code = ch.get("currency_code") or tx.currency.code
                ch_cur = self.fx.get_by_code(ch_cur_code)
                self.db.add(TransactionCharge(
                    transaction=tx,
                    kind=ch.get("kind", "fee"),
                    amount=ch_amount,
                    currency_id=(ch_cur.id if ch_cur else None),
                    description=ch.get("description", ""),
                ))

        # Recompute base_amount/rate if amount or currency changed
        cur_code = tx.currency.code
        rate = self.fx.get_rate(cur_code, base_code) if cur_code != base_code else 1.0
        tx.exchange_rate = rate if cur_code != base_code else None
        tx.base_amount = tx.amount * (rate or 1.0)

        # Keep transfer pair in sync
        if tx.transfer_group_id:
            other = (self.db.query(Transaction)
                     .filter(Transaction.transfer_group_id == tx.transfer_group_id,
                             Transaction.id != tx.id)
                     .first())
            if other and ("amount" in fields or "currency_code" in fields or
                          "transaction_date" in fields or "description" in fields):
                converted = self.fx.convert(tx.amount, cur_code, other.currency.code) or tx.amount
                other.amount = converted
                if "transaction_date" in fields:
                    other.transaction_date = tx.transaction_date
                if "description" in fields and tx.description:
                    other.description = tx.description
                other.updated_at = datetime.now(timezone.utc)

        tx.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(tx)
        return tx

    def delete(self, tx: Transaction):
        """Delete a transaction. If it's one leg of a transfer, delete the other leg too."""
        if tx.transfer_group_id:
            others = (self.db.query(Transaction)
                      .filter(Transaction.transfer_group_id == tx.transfer_group_id,
                              Transaction.id != tx.id)
                      .all())
            for o in others:
                self.db.delete(o)
        self.db.delete(tx)
        self.db.commit()

    def get_by_id(self, tx_id: int) -> Optional[Transaction]:
        return self.db.query(Transaction).filter_by(id=tx_id).first()

    def get_recent(self, limit: int = 50) -> List[Transaction]:
        return (self.db.query(Transaction)
                .order_by(Transaction.transaction_date.desc())
                .limit(limit).all())

    def get_for_account(self, account_id: int, limit: int = 200) -> List[Transaction]:
        return (self.db.query(Transaction)
                .filter_by(account_id=account_id)
                .order_by(Transaction.transaction_date.desc())
                .limit(limit).all())

    def monthly_summary(self, year: int, month: int, base_code: str = "USD") -> Dict:
        from sqlalchemy import extract
        txs = (self.db.query(Transaction)
               .filter(extract("year",  Transaction.transaction_date) == year,
                       extract("month", Transaction.transaction_date) == month)
               .all())
        income = expenses = 0.0
        by_category: Dict[str, float] = {}
        for tx in txs:
            if tx.status == TransactionStatus.CANCELLED:
                continue
            val = tx.base_amount or tx.amount
            ttype = tx.transaction_type
            if ttype in CREDIT_TRANSACTION_TYPES:
                income += val
            elif ttype in DEBIT_TRANSACTION_TYPES:
                expenses += val
                by_category[tx.category] = by_category.get(tx.category, 0) + val
            elif ttype == TransactionType.ADJUSTMENT:
                if val >= 0:
                    income += val
                else:
                    expenses += -val
                    by_category[tx.category] = by_category.get(tx.category, 0) + (-val)

            # Fees/taxes are always an outflow, regardless of transaction direction
            extra = tx.total_fees_taxes
            if extra:
                extra_base = extra
                if tx.currency and tx.currency.code != base_code:
                    extra_base = self.fx.convert(extra, tx.currency.code, base_code) or extra
                expenses += extra_base
                by_category["Fees & Taxes"] = by_category.get("Fees & Taxes", 0) + extra_base
        return {"year": year, "month": month, "income": income,
                "expenses": expenses, "net": income - expenses,
                "by_category": by_category}

    def cash_flow_excluding_transfers(self, base_code: str,
                                       start: Optional[datetime] = None,
                                       end: Optional[datetime] = None) -> Dict:
        """
        Income/expense/by-category totals (in base currency) for the given
        date range, excluding internal transfers between the profile's own
        accounts (and cancelled transactions) — i.e. real revenue and real
        spend, suitable for a cash-flow / P&L view.
        """
        q = self.db.query(Transaction)
        if start is not None:
            q = q.filter(Transaction.transaction_date >= start)
        if end is not None:
            q = q.filter(Transaction.transaction_date < end)

        income = expenses = 0.0
        by_category: Dict[str, float] = {}
        for tx in q.all():
            if tx.transfer_group_id or tx.status == TransactionStatus.CANCELLED:
                continue
            val = tx.base_amount if tx.base_amount is not None else tx.amount
            if tx.base_amount is None and tx.currency and tx.currency.code != base_code:
                val = self.fx.convert(tx.amount, tx.currency.code, base_code) or tx.amount
            if tx.transaction_type in CREDIT_TRANSACTION_TYPES:
                income += val
            elif tx.transaction_type in DEBIT_TRANSACTION_TYPES:
                expenses += val
                by_category[tx.category] = by_category.get(tx.category, 0) + val
        return {"income": income, "expenses": expenses, "net": income - expenses,
                "by_category": by_category}

    def trailing_months_cash_flow(self, base_code: str, n: int = 6) -> List[Dict]:
        """Real income/expense/net (excluding internal transfers) for each
        of the last `n` months, oldest first."""
        from dateutil.relativedelta import relativedelta
        now = datetime.now(timezone.utc)
        result = []
        for i in range(n - 1, -1, -1):
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - relativedelta(months=i)
            month_end = month_start + relativedelta(months=1)
            cf = self.cash_flow_excluding_transfers(base_code, month_start, month_end)
            result.append({"label": month_start.strftime("%b %Y"),
                           "income": cf["income"], "expense": cf["expenses"], "net": cf["net"]})
        return result


# ─── Portfolio Service ────────────────────────────────────────────────────────

class PortfolioService:
    def __init__(self, session: Session, currency_svc: CurrencyService, settings: SettingsService):
        self.db = session
        self.fx = currency_svc
        self.settings = settings

    def add_asset(self, account: Account, asset_type: AssetType, name: str,
                  ticker: str, quantity: float, average_cost: float,
                  currency_code: str, notes: str = "",
                  valuation_factors: str = "",
                  purchase_date: Optional[datetime] = None) -> PortfolioAsset:
        cur = self.fx.get_by_code(currency_code)
        if not cur:
            raise ValueError(f"Currency {currency_code} not found")
        asset = PortfolioAsset(
            account_id=account.id, asset_type=asset_type,
            name=name, ticker=ticker.upper(),
            quantity=quantity, average_cost=average_cost,
            currency_id=cur.id, notes=notes,
            valuation_factors=valuation_factors,
            purchase_date=purchase_date,
        )
        self.db.add(asset)
        self.db.commit()
        self.db.refresh(asset)

        # Seed the trade history with the initial purchase, so it shows up
        # alongside any later BUY/SELL/DIVIDEND trades for analysis.
        if quantity:
            trade = AssetTrade(
                asset_id=asset.id, trade_type="BUY",
                quantity=quantity, price=average_cost, fees=0.0, taxes=0.0,
                trade_date=purchase_date or datetime.now(timezone.utc),
                notes="Initial purchase"
            )
            self.db.add(trade)
            self.db.commit()
        return asset

    def update_asset(self, asset: PortfolioAsset, **fields) -> PortfolioAsset:
        """Edit ticker, name, quantity, average_cost, currency, asset_type, notes."""
        if "currency_code" in fields:
            code = fields.pop("currency_code")
            cur = self.fx.get_by_code(code)
            if not cur:
                raise ValueError(f"Currency {code} not found")
            asset.currency_id = cur.id
        if "ticker" in fields and fields["ticker"]:
            fields["ticker"] = fields["ticker"].upper()
        for key, value in fields.items():
            if hasattr(asset, key):
                setattr(asset, key, value)
        asset.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(asset)
        return asset

    def delete_asset(self, asset: PortfolioAsset):
        self.db.delete(asset)
        self.db.commit()

    def record_trade(self, asset: PortfolioAsset, trade_type: str,
                     quantity: float, price: float, fees: float = 0.0,
                     taxes: float = 0.0,
                     trade_date: Optional[datetime] = None, notes: str = "") -> AssetTrade:
        if trade_date is None:
            trade_date = datetime.now(timezone.utc)
        trade = AssetTrade(
            asset_id=asset.id, trade_type=trade_type,
            quantity=quantity, price=price, fees=fees, taxes=taxes,
            trade_date=trade_date, notes=notes
        )
        # Update average cost on BUY
        if trade_type == "BUY":
            total_cost = (asset.quantity * asset.average_cost) + (quantity * price) + fees + taxes
            asset.quantity += quantity
            asset.average_cost = total_cost / asset.quantity if asset.quantity else price
        elif trade_type == "SELL":
            asset.quantity = max(0.0, asset.quantity - quantity)
        asset.updated_at = datetime.now(timezone.utc)
        self.db.add(trade)
        self.db.commit()
        self.db.refresh(trade)
        return trade

    def update_price(self, asset: PortfolioAsset, price: float):
        asset.current_price = price
        asset.last_price_update = datetime.now(timezone.utc)
        self.db.commit()

    def record_price_snapshot(self, asset: PortfolioAsset, quote: Dict, source: str = "market"):
        """
        Apply a freshly-fetched quote (price + metadata) to `asset`, persist
        the metadata as JSON on the asset for quick display, and append a
        historical AssetPriceSnapshot row so price movement over time can be
        analysed later.
        """
        price = quote.get("price")
        if price is None:
            return
        asset.current_price = price
        asset.last_price_update = datetime.now(timezone.utc)
        asset.price_source = source
        meta = {k: v for k, v in quote.items() if k != "price"}
        asset.market_meta_dict = meta
        snap = AssetPriceSnapshot(
            asset_id=asset.id, price=price,
            currency_code=quote.get("currency", asset.currency.code if asset.currency else ""),
            day_change_pct=quote.get("day_change_pct"),
            day_change_abs=quote.get("day_change_abs"),
            previous_close=quote.get("previous_close"),
            market_cap=quote.get("market_cap"),
            week52_high=quote.get("week52_high"),
            week52_low=quote.get("week52_low"),
            source=source,
        )
        self.db.add(snap)
        self.db.commit()

    def portfolio_summary(self, base_code: str = "USD") -> Dict:
        assets = self.db.query(PortfolioAsset).filter_by(is_active=True).all()
        total_value = total_cost = total_pnl = 0.0
        rows = []
        for a in assets:
            mv = a.market_value
            cb = a.cost_basis
            pnl = a.unrealized_pnl
            mv_base = self.fx.convert(mv, a.currency.code, base_code) or mv
            pnl_base = self.fx.convert(pnl, a.currency.code, base_code) or pnl
            total_value += mv_base
            total_cost  += (self.fx.convert(cb, a.currency.code, base_code) or cb)
            total_pnl   += pnl_base
            rows.append({
                "id": a.id, "name": a.name, "ticker": a.ticker,
                "type": a.asset_type.value, "quantity": a.quantity,
                "avg_cost": a.average_cost, "current_price": a.current_price,
                "market_value": mv, "market_value_base": mv_base,
                "cost_basis": cb, "unrealized_pnl": pnl,
                "pnl_pct": a.pnl_pct, "currency": a.currency.code,
            })
        return {"total_value": total_value, "total_cost": total_cost,
                "total_pnl": total_pnl,
                "pnl_pct": (total_pnl / total_cost * 100) if total_cost else 0,
                "base_currency": base_code, "assets": rows}


# ─── Loan Service ─────────────────────────────────────────────────────────────

class LoanService:
    def __init__(self, session: Session, currency_svc: CurrencyService):
        self.db = session
        self.fx = currency_svc

    def create(self, contact_name: str, direction: str, principal: float,
               currency_code: str, description: str = "",
               due_date: Optional[datetime] = None,
               contact_info: str = "",
               fee_amount: float = 0.0, fee_currency_code: Optional[str] = None,
               fee_description: str = "") -> PersonalLoan:
        cur = self.fx.get_by_code(currency_code)
        if not cur:
            raise ValueError(f"Currency {currency_code} not found")
        fee_cur = self.fx.get_by_code(fee_currency_code) if fee_currency_code else cur
        loan = PersonalLoan(
            contact_name=contact_name, direction=direction,
            principal=principal, currency_id=cur.id,
            description=description, due_date=due_date,
            contact_info=contact_info,
            fee_amount=fee_amount,
            fee_currency_id=(fee_cur.id if fee_cur else None),
            fee_description=fee_description,
        )
        self.db.add(loan)
        self.db.commit()
        self.db.refresh(loan)
        return loan

    def update(self, loan: PersonalLoan, **fields) -> PersonalLoan:
        """Edit contact_name, direction, principal, currency_code, description,
        due_date, contact_info, fee_amount, fee_currency_code, fee_description,
        is_settled."""
        if "currency_code" in fields:
            code = fields.pop("currency_code")
            cur = self.fx.get_by_code(code)
            if not cur:
                raise ValueError(f"Currency {code} not found")
            loan.currency_id = cur.id
        if "fee_currency_code" in fields:
            code = fields.pop("fee_currency_code")
            cur = self.fx.get_by_code(code) if code else loan.currency
            loan.fee_currency_id = cur.id if cur else None
        for key, value in fields.items():
            if hasattr(loan, key):
                setattr(loan, key, value)
        self.db.commit()
        self.db.refresh(loan)
        return loan

    def delete(self, loan: PersonalLoan):
        self.db.delete(loan)
        self.db.commit()

    def record_repayment(self, loan: PersonalLoan, amount: float,
                         repaid_on: Optional[datetime] = None,
                         notes: str = "", fee_amount: float = 0.0) -> LoanRepayment:
        if repaid_on is None:
            repaid_on = datetime.now(timezone.utc)
        rep = LoanRepayment(loan_id=loan.id, amount=amount,
                            fee_amount=fee_amount,
                            repaid_on=repaid_on, notes=notes)
        loan.amount_repaid += amount
        if loan.amount_repaid >= loan.principal:
            loan.is_settled = True
            loan.settled_at = datetime.now(timezone.utc)
        self.db.add(rep)
        self.db.commit()
        self.db.refresh(rep)
        return rep

    def get_all(self, include_settled=False) -> List[PersonalLoan]:
        q = self.db.query(PersonalLoan)
        if not include_settled:
            q = q.filter_by(is_settled=False)
        return q.order_by(PersonalLoan.created_at.desc()).all()

    def summary(self, base_code: str = "USD") -> Dict:
        loans = self.get_all()
        owed_to_me = owed_by_me = 0.0
        for loan in loans:
            out = loan.outstanding
            val = self.fx.convert(out, loan.currency.code, base_code) or out
            if loan.direction == "owed_to_me":
                owed_to_me += val
            else:
                owed_by_me += val
        return {"owed_to_me": owed_to_me, "i_owe": owed_by_me,
                "net": owed_to_me - owed_by_me, "base_currency": base_code}


# ─── Opportunity Service ──────────────────────────────────────────────────────

class OpportunityService:
    """
    Tracks 'attempts' to gain (or take on) money — credit card applications,
    loans, mortgages, investments, new income, business ventures, etc.
    """
    def __init__(self, session: Session, currency_svc: CurrencyService):
        self.db = session
        self.fx = currency_svc

    def create(self, title: str, category: OpportunityCategory,
              direction: OpportunityDirection,
              status: OpportunityStatus = OpportunityStatus.CONSIDERING,
              institution: str = "", estimated_value: Optional[float] = None,
              currency_code: Optional[str] = None,
              interest_rate: Optional[float] = None,
              applied_date: Optional[datetime] = None,
              decision_date: Optional[datetime] = None,
              description: str = "", notes: str = "") -> Opportunity:
        cur = self.fx.get_by_code(currency_code) if currency_code else None
        opp = Opportunity(
            title=title, category=category, direction=direction, status=status,
            institution=institution, estimated_value=estimated_value,
            currency_id=(cur.id if cur else None),
            interest_rate=interest_rate, applied_date=applied_date,
            decision_date=decision_date, description=description, notes=notes,
        )
        self.db.add(opp)
        self.db.commit()
        self.db.refresh(opp)
        return opp

    def update(self, opp: Opportunity, **fields) -> Opportunity:
        if "currency_code" in fields:
            code = fields.pop("currency_code")
            cur = self.fx.get_by_code(code) if code else None
            opp.currency_id = cur.id if cur else None
        for key, value in fields.items():
            if hasattr(opp, key):
                setattr(opp, key, value)
        opp.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(opp)
        return opp

    def delete(self, opp: Opportunity):
        self.db.delete(opp)
        self.db.commit()

    def get_all(self, status: Optional[OpportunityStatus] = None,
               category: Optional[OpportunityCategory] = None,
               direction: Optional[OpportunityDirection] = None) -> List[Opportunity]:
        q = self.db.query(Opportunity)
        if status:
            q = q.filter_by(status=status)
        if category:
            q = q.filter_by(category=category)
        if direction:
            q = q.filter_by(direction=direction)
        return q.order_by(Opportunity.created_at.desc()).all()

    def link_account(self, opp: Opportunity, account: Account):
        opp.linked_account_id = account.id
        opp.status = OpportunityStatus.ACTIVE
        self.db.commit()


# ─── Department Service (cost centers / business units) ───────────────────────

class DepartmentService:
    def __init__(self, session: Session):
        self.db = session

    def get_all(self) -> List["Department"]:
        from src.models.database import Department
        return self.db.query(Department).order_by(Department.name).all()

    def get(self, dept_id: int):
        from src.models.database import Department
        return self.db.query(Department).get(dept_id)

    def create(self, name: str, color: str = "#4A90D9", description: str = "") -> "Department":
        from src.models.database import Department
        name = name.strip()
        if not name:
            raise ValueError("Department name cannot be empty")
        existing = self.db.query(Department).filter_by(name=name).first()
        if existing:
            return existing
        dept = Department(name=name, color=color, description=description)
        self.db.add(dept)
        self.db.commit()
        self.db.refresh(dept)
        return dept

    def update(self, dept: "Department", **fields) -> "Department":
        for k, v in fields.items():
            if hasattr(dept, k):
                setattr(dept, k, v)
        self.db.commit()
        return dept

    def delete(self, dept: "Department"):
        # Detach accounts/transactions referencing this department rather
        # than blocking the delete.
        from src.models.database import Account, Transaction
        self.db.query(Account).filter_by(department_id=dept.id).update({"department_id": None})
        self.db.query(Transaction).filter_by(department_id=dept.id).update({"department_id": None})
        self.db.delete(dept)
        self.db.commit()

    def cash_flow_summary(self, base_code: str, months: int = 1) -> List[dict]:
        """
        Net cash flow (income - expenses, in base currency) per department
        over the trailing `months` months, including an "Unassigned" bucket
        for transactions with no department. Internal transfers between the
        business's own accounts are excluded — they're not real revenue or
        spend.
        """
        from src.models.database import Transaction, CREDIT_TRANSACTION_TYPES, DEBIT_TRANSACTION_TYPES
        from dateutil.relativedelta import relativedelta
        cutoff = datetime.now(timezone.utc) - relativedelta(months=months)
        depts = self.get_all()
        result = []
        for dept in [None] + depts:
            q = self.db.query(Transaction).filter(Transaction.transaction_date >= cutoff)
            q = q.filter(Transaction.department_id == (dept.id if dept else None))
            income = expense = 0.0
            for tx in q.all():
                if tx.transfer_group_id:
                    continue  # internal transfer between own accounts
                amt = tx.base_amount if tx.base_amount is not None else tx.amount
                if tx.transaction_type in CREDIT_TRANSACTION_TYPES:
                    income += amt
                elif tx.transaction_type in DEBIT_TRANSACTION_TYPES:
                    expense += amt
            result.append({
                "name": dept.name if dept else "Unassigned",
                "color": dept.color if dept else "#999999",
                "income": income, "expense": expense, "net": income - expense,
            })
        return result


# ─── Attachment Service ───────────────────────────────────────────────────────

class AttachmentService:
    # WealthMap stores user-provided proof files of any kind (photos, scans,
    # PDFs, spreadsheets, contracts, etc.). Rather than restrict to a fixed
    # allowlist, we just block a small set of executable/script extensions
    # for basic safety — everything else is accepted.
    BLOCKED_TYPES = {
        ".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".ps1", ".vbs", ".sh"
    }

    def __init__(self, attachments_dir: str):
        self.base_dir = Path(attachments_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_file(self, source_path: str, db: Session,
                  owner_type: str, owner_id: int,
                  description: str = "") -> Attachment:
        src = Path(source_path)
        if not src.exists():
            raise FileNotFoundError(f"File not found: {source_path}")
        ext = src.suffix.lower()
        if ext in self.BLOCKED_TYPES:
            raise ValueError(f"File type {ext} is not allowed for safety reasons")

        # Store under a UUID name to avoid collisions
        stored_name = f"{uuid.uuid4().hex}{ext}"
        dest = self.base_dir / stored_name
        shutil.copy2(src, dest)

        # SHA-256 checksum
        sha = hashlib.sha256()
        with open(dest, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        checksum = sha.hexdigest()

        mime = mimetypes.guess_type(str(src))[0] or "application/octet-stream"
        size = dest.stat().st_size

        att = Attachment(
            original_filename=src.name,
            stored_filename=stored_name,
            file_path=str(dest),
            mime_type=mime,
            file_size=size,
            checksum=checksum,
            description=description,
        )
        # Wire FK
        if owner_type == "account":
            att.account_id = owner_id
        elif owner_type == "transaction":
            att.transaction_id = owner_id
        elif owner_type == "trade":
            att.trade_id = owner_id
        elif owner_type == "loan":
            att.loan_id = owner_id
        elif owner_type == "repayment":
            att.repayment_id = owner_id
        elif owner_type == "receipt":
            att.receipt_id = owner_id
        elif owner_type == "opportunity":
            att.opportunity_id = owner_id
        elif owner_type == "asset":
            att.asset_id = owner_id

        db.add(att)
        db.commit()
        db.refresh(att)
        return att

    def delete_file(self, attachment: Attachment, db: Session):
        p = Path(attachment.file_path)
        if p.exists():
            p.unlink()
        db.delete(attachment)
        db.commit()

    def open_file(self, attachment: Attachment):
        import subprocess, sys
        p = attachment.file_path
        if sys.platform.startswith("win"):
            os.startfile(p)
        elif sys.platform == "darwin":
            subprocess.run(["open", p])
        else:
            subprocess.run(["xdg-open", p])


# ─── App Context (single injection point) ────────────────────────────────────

class AppContext:
    """Owns DB session and all services — passed into every UI panel."""

    def __init__(self, data_dir: str, profile: Optional[dict] = None, registry=None):
        from src.models.database import init_db
        self.data_dir   = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        db_path         = str(self.data_dir / "wealthmap.db")
        att_dir         = str(self.data_dir / "attachments")
        engine, SessionLocal = init_db(db_path)
        self.session    = SessionLocal()

        # Multi-profile context. `profile` is a dict from ProfileRegistry:
        # {"id", "name", "type": "personal"|"business", "linked": [...]}.
        # Falls back to a synthetic "Personal" profile for callers that
        # don't go through the launcher (e.g. tests, scripts).
        self.profile    = profile or {"id": "default", "name": "Personal",
                                      "type": "personal", "linked": []}
        self.registry   = registry
        self.is_business = self.profile.get("type") == "business"

        # services
        self.settings   = SettingsService(self.session)
        self.currency   = CurrencyService(self.session, self.settings)
        self.account    = AccountService(self.session, self.currency, self.settings)
        self.transaction= TransactionService(self.session, self.currency, self.settings)
        self.portfolio  = PortfolioService(self.session, self.currency, self.settings)
        self.loan       = LoanService(self.session, self.currency)
        self.opportunity= OpportunityService(self.session, self.currency)
        self.attachment = AttachmentService(att_dir)
        self.customization = CustomizationService(self.session)
        self.department = DepartmentService(self.session)

        from src.services.market_data import MarketDataService
        self.market_data = MarketDataService()

        # Google Drive backup (needs the profile *registry*, not just this
        # profile's session, since a backup covers every profile under the
        # data root). Only available when we actually have a registry —
        # e.g. not for standalone scripts/tests that construct AppContext
        # directly against a bare data_dir.
        self.backup = None
        if self.registry is not None:
            from src.services.backup_service import GoogleDriveBackupService
            self.backup = GoogleDriveBackupService(self.registry)
            from sqlalchemy import event as _sa_event

            def _on_commit(_session):
                if self.backup:
                    self.backup.mark_dirty()

            _sa_event.listen(self.session, "after_commit", _on_commit)

        self._first_run()

        # Apply saved theme preference (UI reads this before building widgets)
        from src.ui.theme import theme
        saved_mode = self.settings.get("theme_mode")
        if saved_mode:
            theme.set_mode(saved_mode)

    def _first_run(self):
        # Always seed/update currencies so new ones appear in existing databases
        self.currency.seed_currencies()
        if not self.settings.get("initialized"):
            if not self.settings.get("base_currency"):
                self.settings.set("base_currency", "USD")
            self.settings.set("initialized", True)
            # New profiles start completely empty — the user adds their own
            # accounts, transactions, departments, etc. (_seed_demo_personal
            # / _seed_demo_business below are kept for potential future use,
            # e.g. an opt-in "load sample data" action, but aren't called
            # automatically.)

    def _seed_demo_personal(self):
        """Add a few starter accounts so the app isn't empty on first launch."""
        try:
            chequing = self.account.create(
                "Main Chequing", AccountType.BANK, "USD",
                institution="My Bank", color="#4A90D9"
            )
            wallet = self.account.create(
                "Physical Wallet", AccountType.WALLET, "USD", color="#7ED321"
            )
            portfolio = self.account.create(
                "Investment Portfolio", AccountType.PORTFOLIO, "USD",
                institution="My Broker", color="#9B59B6"
            )
            savings = self.account.create(
                "Savings Account", AccountType.SAVINGS, "USD",
                institution="My Bank", color="#F5A623"
            )
            credit_card = self.account.create(
                "Rewards Credit Card", AccountType.CREDIT_CARD, "USD",
                institution="My Bank", color="#E74C3C",
                credit_limit=5000.0, statement_day=28,
                payment_due_day=15, interest_rate=21.99
            )

            # Sample transactions
            now = datetime.now(timezone.utc)
            self.transaction.add(chequing, TransactionType.INCOME, 3500.0,
                "Monthly salary", "Salary / Income", "Employer Inc",
                transaction_date=now.replace(day=1))
            self.transaction.add(chequing, TransactionType.EXPENSE, 1200.0,
                "Rent payment", "Housing & Rent", "Landlord",
                transaction_date=now.replace(day=3))
            self.transaction.add(chequing, TransactionType.EXPENSE, 89.50,
                "Weekly groceries", "Groceries", "Supermarket",
                transaction_date=now.replace(day=7))
            self.transaction.add(wallet, TransactionType.INCOME, 200.0,
                "ATM withdrawal", "Transfer", "",
                transaction_date=now.replace(day=5))
            self.transaction.add(credit_card, TransactionType.EXPENSE, 64.30,
                "Dinner out", "Food & Dining", "Bistro 22",
                transaction_date=now.replace(day=9),
                fee_amount=0.0, tax_amount=5.30, tax_description="Sales tax")

            # Sample receipts (one linked to a transaction, one standalone)
            usd_cur = self.currency.get_by_code("USD")
            groceries_tx = (self.session.query(Transaction)
                            .filter_by(description="Weekly groceries").first())
            self.session.add(Receipt(
                title="Weekly groceries", merchant="Supermarket", amount=89.50,
                currency_id=usd_cur.id if usd_cur else None,
                receipt_date=now.replace(day=7), category="Groceries",
                transaction_id=groceries_tx.id if groceries_tx else None,
                notes="Paper receipt — scan and attach when available."
            ))
            self.session.add(Receipt(
                title="Bistro 22 dinner", merchant="Bistro 22", amount=64.30,
                currency_id=usd_cur.id if usd_cur else None,
                receipt_date=now.replace(day=9), category="Food & Dining",
                notes="Includes $5.30 sales tax — see Fees & Taxes report."
            ))
            self.session.commit()

            # Sample asset
            asset = self.portfolio.add_asset(
                portfolio, AssetType.STOCK, "Apple Inc.", "AAPL",
                10, 150.0, "USD"
            )
            self.portfolio.update_price(asset, 175.0)

            # Sample loan
            self.loan.create("Alex Johnson", "owed_to_me", 250.0, "USD",
                             "Lunch money from last month", contact_info="alex@example.com")
        except Exception as e:
            print(f"[Demo seed] {e}")

    def _seed_demo_business(self):
        """
        Seed a Business profile with department-tagged accounts and
        transactions, AR/AP entries, and an opportunity — so a CEO opening
        WealthMap for the first time sees what a populated Cash Flow
        Command Center looks like.
        """
        try:
            from src.models.database import Department, OpportunityCategory, OpportunityDirection

            # Departments / cost centers
            sales = self.department.create("Sales", "#4A90D9", "Revenue-generating sales team")
            eng   = self.department.create("Engineering", "#9B59B6", "Product & engineering")
            ops   = self.department.create("Operations", "#F5A623", "Operations & admin")
            mkt   = self.department.create("Marketing", "#E74C3C", "Marketing & growth")

            # Core accounts
            operating = self.account.create(
                "Business Operating Account", AccountType.BANK, "USD",
                institution="Business Bank", color="#4A90D9",
                description="Primary operating account for day-to-day cash flow"
            )
            payroll = self.account.create(
                "Payroll Account", AccountType.BANK, "USD",
                institution="Business Bank", color="#9B59B6",
                description="Funded ahead of each payroll run"
            )
            tax_reserve = self.account.create(
                "Tax Reserve", AccountType.SAVINGS, "USD",
                institution="Business Bank", color="#F5A623",
                description="Set-aside funds for quarterly tax payments — do not spend"
            )
            biz_card = self.account.create(
                "Corporate Card", AccountType.CREDIT_CARD, "USD",
                institution="Business Bank", color="#E74C3C",
                credit_limit=25000.0, statement_day=28, payment_due_day=15,
                interest_rate=19.99,
                description="Shared corporate card for operating expenses"
            )

            now = datetime.now(timezone.utc)

            # Revenue (Sales department)
            acme_tx = self.transaction.add(operating, TransactionType.INCOME, 48000.0,
                "Client invoice — Acme Corp (monthly retainer)", "Salary / Income",
                "Acme Corp", transaction_date=now.replace(day=2))
            acme_tx.department_id = sales.id
            new_tx = self.transaction.add(operating, TransactionType.INCOME, 18500.0,
                "Client invoice — Globex Ltd (project milestone)", "Salary / Income",
                "Globex Ltd", transaction_date=now.replace(day=10))
            if new_tx:
                new_tx.department_id = sales.id

            # Payroll funding + run (Engineering + Operations + Marketing)
            self.transaction.add(operating, TransactionType.TRANSFER, 32000.0,
                "Fund payroll account", "Transfer", "",
                transaction_date=now.replace(day=24), linked_account=payroll)

            payroll_eng = self.transaction.add(payroll, TransactionType.EXPENSE, 18000.0,
                "Engineering payroll", "Business", "Payroll Provider",
                transaction_date=now.replace(day=25))
            payroll_eng.department_id = eng.id

            payroll_ops = self.transaction.add(payroll, TransactionType.EXPENSE, 7000.0,
                "Operations payroll", "Business", "Payroll Provider",
                transaction_date=now.replace(day=25))
            payroll_ops.department_id = ops.id

            payroll_mkt = self.transaction.add(payroll, TransactionType.EXPENSE, 7000.0,
                "Marketing payroll", "Business", "Payroll Provider",
                transaction_date=now.replace(day=25))
            payroll_mkt.department_id = mkt.id

            # Operating expenses (mixed departments)
            cloud = self.transaction.add(operating, TransactionType.EXPENSE, 4200.0,
                "Cloud infrastructure (AWS)", "Business", "Amazon Web Services",
                transaction_date=now.replace(day=5))
            cloud.department_id = eng.id

            ads = self.transaction.add(operating, TransactionType.EXPENSE, 6500.0,
                "Digital ad campaign", "Business", "Google Ads",
                transaction_date=now.replace(day=8))
            ads.department_id = mkt.id

            rent = self.transaction.add(operating, TransactionType.EXPENSE, 5200.0,
                "Office rent", "Housing & Rent", "Landlord Properties",
                transaction_date=now.replace(day=1))
            rent.department_id = ops.id

            self.transaction.add(biz_card, TransactionType.EXPENSE, 1480.0,
                "Software subscriptions (SaaS tools)", "Subscription", "Various Vendors",
                transaction_date=now.replace(day=6))

            # Tax set-aside
            self.transaction.add(operating, TransactionType.TRANSFER, 9000.0,
                "Quarterly tax set-aside", "Transfer", "",
                transaction_date=now.replace(day=15), linked_account=tax_reserve)

            self.session.commit()

            # Accounts Receivable (clients who owe the business) and
            # Accounts Payable (vendors the business owes) — modeled via
            # the existing Personal Loans infrastructure, relabeled
            # "Receivables & Payables" for business profiles.
            self.loan.create("Acme Corp", "owed_to_me", 12000.0, "USD",
                             "Outstanding invoice #1042 — net 30",
                             contact_info="ap@acmecorp.com")
            self.loan.create("Globex Ltd", "owed_to_me", 18500.0, "USD",
                             "Project milestone invoice — due in 15 days",
                             contact_info="finance@globex.com")
            self.loan.create("Initech Supplies", "i_owe", 3200.0, "USD",
                             "Office supplies & equipment — due in 10 days",
                             contact_info="billing@initech.com")
            self.loan.create("Cloud Hosting Partner", "i_owe", 4200.0, "USD",
                             "Monthly infrastructure invoice — due in 20 days",
                             contact_info="billing@cloudpartner.com")

            # A growth opportunity, so Opportunities isn't empty either
            self.opportunity.create(
                title="Series A Funding Round", category=OpportunityCategory.INVESTMENT,
                direction=OpportunityDirection.ASSET,
                estimated_value=2_000_000.0, currency_code="USD",
                institution="Northbridge Ventures",
                description="Term sheet under review — would extend runway ~18 months.",
                notes="Follow up with legal on due-diligence checklist."
            )
        except Exception as e:
            print(f"[Demo seed - business] {e}")

    def cross_profile_transfer(self, account: Account, tx_type: TransactionType, amount: float,
                               description: str, category: str,
                               target_profile_id: str, target_account_id: int,
                               transaction_date: Optional[datetime] = None,
                               currency_code: Optional[str] = None,
                               payee: str = "", reference: str = "", notes: str = "",
                               status: Optional[TransactionStatus] = None,
                               fee_amount: float = 0.0, fee_currency_code: Optional[str] = None,
                               fee_description: str = "",
                               tax_amount: float = 0.0, tax_currency_code: Optional[str] = None,
                               tax_description: str = "",
                               charges: Optional[List[dict]] = None,
                               custom_type_label: Optional[str] = None,
                               department_id: Optional[int] = None) -> Transaction:
        """
        Move money between this profile's account and an account in a
        *linked* profile of the same type. Creates one transaction leg in
        each profile's database (each gets its own row — there's no
        cross-database foreign key), sharing a `transfer_group_id` and
        cross-referencing each other via `linked_profile_id` /
        `linked_account_label`.
        """
        if not self.registry:
            raise ValueError("No profile registry available for cross-profile transfers")
        target_profile = self.registry.get_profile(target_profile_id)
        if not target_profile:
            raise ValueError("Target profile not found")
        if target_profile["type"] != self.profile["type"]:
            raise ValueError("Can only transfer between profiles of the same type")
        if target_profile_id not in self.profile.get("linked", []):
            raise ValueError("Profiles must be linked for cross-profile transfers")

        transfer_group_id = uuid.uuid4().hex
        cur_code = currency_code or account.currency.code

        local_tx = self.transaction.add(
            account=account, tx_type=tx_type, amount=amount,
            description=description, category=category, payee=payee, reference=reference,
            transaction_date=transaction_date, currency_code=cur_code,
            status=status or TransactionStatus.CLEARED, notes=notes,
            fee_amount=fee_amount, fee_currency_code=fee_currency_code, fee_description=fee_description,
            tax_amount=tax_amount, tax_currency_code=tax_currency_code, tax_description=tax_description,
            charges=charges, custom_type_label=custom_type_label, department_id=department_id,
            transfer_group_id_override=transfer_group_id,
            linked_profile_id=target_profile_id,
            linked_account_label=target_profile["name"],  # placeholder, filled in below
        )

        # Briefly open the linked profile's database to create the
        # mirrored leg there.
        remote_ctx = AppContext(str(self.registry.data_dir(target_profile_id)),
                                profile=target_profile, registry=self.registry)
        try:
            remote_acc = remote_ctx.session.query(Account).get(target_account_id)
            if not remote_acc:
                raise ValueError("Target account not found in the linked profile")

            if tx_type == TransactionType.TRANSFER or tx_type in DEBIT_TRANSACTION_TYPES:
                mirror_type, prefix = TransactionType.INCOME, "Transfer from"
            else:
                mirror_type, prefix = TransactionType.EXPENSE, "Transfer to"

            converted = remote_ctx.currency.convert(amount, cur_code, remote_acc.currency.code) or amount
            remote_ctx.transaction.add(
                account=remote_acc, tx_type=mirror_type, amount=converted,
                description=description or f"{prefix} {self.profile['name']}: {account.name}",
                category="Transfer", transaction_date=transaction_date,
                currency_code=remote_acc.currency.code,
                transfer_group_id_override=transfer_group_id,
                linked_profile_id=self.profile["id"],
                linked_account_label=f"{self.profile['name']}: {account.name}",
            )
            remote_account_name = remote_acc.name
        finally:
            remote_ctx.session.close()

        local_tx.linked_account_label = f"{target_profile['name']}: {remote_account_name}"
        self.session.commit()
        return local_tx

    def fetch_rates_background(self):
        """Non-blocking rate fetch."""
        def _fetch():
            base = self.settings.get("base_currency", "USD")
            self.currency.fetch_rates_online(base)
        t = threading.Thread(target=_fetch, daemon=True)
        t.start()
