# 💰 WealthMap — Personal & Business Finance Manager

> *Always know where your money is, where it's working, and where it's sitting.*

WealthMap is a **local-first** finance desktop application built with Python.
All data lives on **your machine** — no cloud, no subscriptions, no ads.

On launch, choose which **profile** to open — or create a new one:
- **Personal** profiles work like a traditional personal finance app.
- **Business** profiles unlock a CEO-focused experience: department cost
  centers, a Cash Flow Command Center with burn rate & runway, and
  Receivables/Payables tracking.

Profiles of the same type can be **linked** (at creation, or later from
Settings) so a transaction can move money directly between an account in one
linked profile and an account in another — e.g. between two personal
profiles, or between two business entities.

---

## ✨ Features

| Module | What it does |
|--------|-------------|
| **Dashboard** | Net worth at a glance, monthly cash flow, recent transactions — every stat card is clickable and drills into the relevant panel |
| **Accounts** | Bank accounts, physical wallet, savings, crypto wallets, investment portfolios, and **credit cards** (limit, statement/due dates, APR, utilization bar) — fully editable, deletable, with **file attachments** |
| **Transactions** | A huge range of built-in transaction types — plus **your own custom types and categories** — every transaction is editable and deletable, with an **unlimited number of additional fees/taxes**, **inline table editing**, the option for **any transaction type to involve a second account** (including a **linked profile's** account), and department tagging on Business profiles |
| **Portfolio** | Stocks, ETFs, bonds, mutual funds, crypto, commodities, real estate & other — cost basis, unrealized P&L, a **known-asset picker** that auto-fills name & ticker, **live market metadata** saved on every refresh for later analysis, **valuation factors** for real estate/other, file attachments, and **inline table editing** |
| **Loans** *(Personal)* / **Receivables & Payables** *(Business)* | Who owes you, who you owe — for Business profiles this becomes Accounts Receivable / Accounts Payable for clients & vendors — editable, with optional fees, a "show settled" toggle, and base-currency equivalents |
| **Receipts** | Store receipts with file attachments, optionally **linked to a transaction**, with spend summary cards and **inline table editing** |
| **Exchange Rates** | Live rates (auto-fetched) + manual override + converter — hover any currency to see its country & common name |
| **Wealth Journey** *(Personal)* / **Financial Journey** *(Business)* | Net worth trend (12 months) + 6-month forecast, income vs expenses, category breakdown, yearly summary |
| **Departments** *(Business only)* | Cost centers / business units — tag accounts and transactions to see department-level cash flow & P&L |
| **Cash Flow Command Center** *(Business only)* | Live KPIs: cash position, burn rate, runway, MTD revenue & margin, AR/AP — plus revenue-vs-expense trend, department cash flow chart, and top expense categories |
| **Opportunities** | Track attempts to gain assets or take on liabilities — credit card applications, loans, mortgages, investments, new income, business ventures — with status, **any number of file attachments of any type**, and one-click linking to a real account once approved |
| **Reports** | PDF/Excel reports including a dedicated **Fees & Taxes report** (covers primary fees/taxes *and* every additional charge) |
| **Settings** | Profile management (rename, link/unlink, switch), base currency, **custom categories & transaction types**, default landing page, base-currency-equivalent toggle, CSV export, DB backup, **light/dark theme** |

### 🗂️ Multi-Profile: Personal & Business
On every launch, a profile picker lets you open an existing profile or
create a new **Personal** or **Business** one — this is always shown first,
even if you only have one profile. Each profile is fully isolated — its own
database and attachments — under `~/WealthMap/profiles/<id>/`. Existing
single-profile installs are migrated automatically into a "Personal" profile
the first time you run this version.

New profiles start **completely empty** — no demo accounts or transactions —
since you haven't told WealthMap anything about them yet. Add your own
accounts, transactions, and (for Business profiles) departments from there.
Both creating and opening a profile show a brief loading animation while the
profile's database is initialized.

### 🔀 Switch / New Profile, from anywhere
While inside a profile, the top-left of the sidebar has a
"🔀 Switch / New Profile" button — it opens a small picker listing all your
Personal and Business profiles (with the current one marked), lets you jump
straight to any of them, or create a new Personal/Business profile on the
spot. "Manage Profiles…" returns to the full profile picker screen.

### 🔗 Linked Profiles & Cross-Profile Transfers
Profiles of the **same type** (Personal-Personal or Business-Business) can be
linked — offered when you create a new profile, and manageable anytime from
Settings → Profile. Once linked, the "Also Affects Account" field in the
Transaction form includes the linked profile's accounts (shown as
"[Profile Name] Account Name"). Selecting one creates a transaction in *both*
profiles' databases — with currency conversion if needed — so e.g. a transfer
from your personal checking account can land directly in your side-business's
operating account.



### ✏️ Inline Table Editing
On the Transactions, Portfolio, and Receipts panels, click **"✎ Edit"** on
any row to turn it into an editable row right in the table — change the
date, description, category, amount, and more — then click **✓** to save or
**✕** to cancel, without leaving the table.

### 🏷️ Custom Categories & Transaction Types
Add your own transaction categories from Settings (or on the fly from the
transaction form's category dropdown). You can also define entirely new
**transaction types** — give them a name and choose whether they increase
your balance (like income), decrease it (like an expense), or accept a
signed amount either way — and they'll appear in the Type dropdown right
alongside the built-ins.

### 🔗 Any Transaction Can Involve a Second Account
Every transaction — not just transfers — has an optional "Also Affects
Account" field. Set it and WealthMap records a mirrored entry on that other
account too (e.g. funding an Investment from your checking account, or a
cash Withdrawal that lands in a Wallet account), with automatic currency
conversion if the two accounts use different currencies.

### 💱 Base-Currency Equivalents, Wherever They're Useful
Whenever an amount is shown in a currency other than your base currency —
transaction amounts, receipt totals, portfolio cost/price, loan balances —
WealthMap also shows the equivalent in your base currency, e.g.
"€92.50 (≈ $100.00)". Turn this off in Settings → Appearance if you'd
rather see amounts in their native currency only.

### ⚙️ More Settings
Settings now also includes: a default landing page (choose which panel
WealthMap opens on), a toggle for base-currency equivalents, and management
screens for your custom categories and transaction types.

### ✨ Futuristic Loading Animation
Switching panels (or toggling the theme) now briefly shows an animated
loading screen — a rotating dual-arc ring with a pulsing core, a scanning
baseline, and animated "LOADING..." text in your accent color — before the
panel appears.

### 📅 Purchase Date & Time, and Auto-Filled Prices
When adding a Stock, ETF, Mutual Fund, Crypto, Commodity, Bond, Real Estate,
or Other asset, you can now record the date and time you purchased it — this
seeds the asset's trade history so it's there for later analysis. And when
you pick a name from the **Known Asset** list, WealthMap immediately fetches
its current price and currency and fills in "Average Cost / Unit" for you
(you can still adjust it if you paid a different price).

### 🌐 More Reliable Live Prices
Price refresh now tries multiple sources in order — an optional `yfinance`
package if installed, a direct Yahoo Finance lookup that needs no extra
package, and (for crypto) CoinGecko — and crypto tickers like "BTC" are
automatically expanded to "BTC-USD". If a ticker still can't be priced, the
refresh dialog now explains *why* for each one (e.g. "ticker not found" vs.
"network error"), so you can tell at a glance whether it's a typo or a
connectivity issue.

### 📎 Attach Files Right From Create/Edit
The New/Edit forms for Transactions, Portfolio Assets, Opportunities, and
Receipts now include a full "📎 Attachments" section — attach as many files
of any type as you like, and remove any of them, without leaving the form.
For new entries, files are staged and uploaded the moment you save; for
existing ones, changes apply immediately.

### ➕ Unlimited Additional Fees & Taxes
Every transaction still has its primary "Fee" and "Tax" fields, but you can
now click **"＋ Add Another Fee / Tax"** as many times as you like to record
any number of additional charges — each with its own kind (fee or tax),
amount, currency, and description. All of these roll up into the
transaction's total and into the Fees & Taxes report.

### 📈 Known-Asset Picker & Persistent Market Metadata
When adding a Stock, ETF, Mutual Fund, Crypto, or Commodity asset, pick from
a curated list of well-known names (Apple, Vanguard S&P 500 ETF, Bitcoin,
Gold, etc.) and the name & ticker are filled in automatically — or just type
your own. Every time you click **⟳ Refresh Prices**, WealthMap stores the
full quote (day change %, previous close, market cap, 52-week range) on the
asset *and* appends a timestamped snapshot to that asset's price history, so
you can analyse how it's moved over time.

### 🏠 Valuation Factors for Real Estate & Other Assets
Real Estate and "Other" assets don't have a live market price, so their edit
screen includes a free-form **Valuation Factors** box — jot down location,
size, condition, comparable sales, last appraisal date, renovations, or
anything else that affects what the asset is worth.

### 📎 Attach Proof Files — Everywhere
Accounts, transactions, portfolio assets, loans, receipts, and opportunities
all let you attach supporting files — and opportunities/receipts/assets
support attaching **any number of files, of any type** (statements, deeds,
contracts, screenshots, scans...), with the ability to open or remove each
one individually at any time.

### 💳 Credit Cards
Add a Credit Card account with a credit limit, statement closing day, payment due day,
and APR. The account card shows what you owe, your available credit, and a
utilization bar. Paying off the card is just a normal transfer from another
account — no special workflow needed.

### 🌓 Light & Dark Theme
Toggle the theme from the sidebar switch (or Settings → Appearance). The change
applies instantly across every panel, chart, and dialog in the app, and your
preference is remembered between sessions.

### 🌍 Global Currency Support
Nearly 100 currencies are built in, including West & Central African CFA francs
(XAF, XOF), Nigerian Naira, Kenyan Shilling, and a wide range of Southeast &
South Asian currencies (PHP, THB, VND, IDR, MYR, KRW, INR, PKR, BDT, and more).
Hover over any currency code in a dropdown to see the issuing country and the
currency's common nickname (e.g. "Piso", "Naira", "CFA Franc").

### 🔁 Multi-Account & Multi-Currency Transfers
Move money between any two accounts — even if they're in different currencies.
WealthMap converts the amount using the latest exchange rate and shows a live
preview before you save. Add an optional transfer fee and/or tax, each with its
own currency and description; both legs of the transfer stay in sync if you
later edit or delete it.

### 💰 Fees & Taxes, Everywhere
Transactions, loans (and their repayments), and portfolio trades can all carry
fees and/or taxes. These are subtracted from account balances automatically and
rolled up into a dedicated **Fees & Taxes report** so you can see exactly how
much "extra" you're paying.

### 📈 Live Market Data
Click **⟳ Refresh Prices** on the Portfolio panel to pull current prices for
stocks, ETFs, bonds, mutual funds, commodities, and crypto (via Yahoo Finance,
with a CoinGecko fallback for crypto). Each holding shows whether its price is
from the live market or entered manually. Real Estate and "Other" assets remain
manual-valuation only.

### 📊 Wealth Journey
A dedicated analytics panel shows your net worth trend over the last 12 months,
a simple 6-month forecast based on your average cash flow, monthly income vs.
expenses, this month's spending by category, and a 3-year yearly summary with
savings rate.

### 🎯 Opportunities
Log every attempt to grow your wealth — or take on new debt — in one place:
credit card applications, loans, mortgages, investments, new income streams,
business ventures, insurance policies, and more. Track status from
"Considering" through "Approved"/"Active", attach supporting documents (offer
letters, applications, contracts), and link an opportunity to a real account
once it becomes active.

### 📐 Responsive Layout
The app adapts to your window size — account and opportunity cards reflow into
more or fewer columns as you resize the window, and the sidebar scrolls on
short screens.

### File Attachments
Every entity (transaction, loan, receipt, trade, opportunity) supports
**attached proof files**:
- PDF bank statements
- Receipt photos (JPG, PNG, WEBP)
- Word/Excel documents
- CSV exports
- Any file up to the OS limit

Files are stored in this profile's `attachments/` folder with SHA-256 checksums.

---

## 🚀 Quick Start

### 1. Install Python 3.11+
Download from [python.org](https://python.org)

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

On Linux you may also need:
```bash
sudo apt install python3-tk   # Ubuntu/Debian
sudo dnf install python3-tkinter  # Fedora
```

### 3. Run
```bash
python main.py
```

Data is stored in `~/WealthMap/` by default.
To use a custom location:
```bash
WEALTHMAP_DATA=/my/path python main.py
```

---

## 📁 Project Structure

```
wealthmap/
├── main.py                  # Entry point
├── requirements.txt
└── src/
    ├── models/
    │   └── database.py      # SQLAlchemy ORM models
    ├── services/
    │   ├── core.py             # Business logic, services
    │   ├── market_data.py      # Live price fetching (yfinance / CoinGecko)
    │   ├── report_engine.py    # PDF/Excel report building blocks
    │   └── report_generators.py# Per-module report generators
    └── ui/
        ├── app.py           # Main window, navigation, theme switching
        ├── theme.py         # Light/dark colour palettes
        ├── widgets.py        # Shared UI components
        ├── dashboard.py      # Overview panel (clickable stat cards)
        ├── accounts.py       # Account management (incl. credit cards)
        ├── transactions.py   # Transaction ledger (transfers, fees, taxes)
        ├── portfolio.py       # Investment holdings + live prices
        ├── loans.py            # Personal loans & debts
        ├── receipts.py         # Receipt storage, linked to transactions
        ├── exchange.py         # Currency rates & converter
        ├── analytics.py        # Wealth Journey panel
        ├── opportunities.py    # Opportunities / wealth-building attempts
        ├── reports_panel.py
        └── settings_panel.py
```

---

## 🗃️ Data Storage

Everything lives in `~/WealthMap/`, organized per profile:

```
~/WealthMap/
├── profiles.json              # profile registry (names, types, links)
└── profiles/
    ├── <profile-id-1>/
    │   ├── wealthmap.db        # SQLite database for this profile
    │   └── attachments/        # Attached files (receipts, statements, etc.)
    │       ├── a3f2b1c4...pdf
    │       └── 9d8e7f6a...jpg
    └── <profile-id-2>/
        ├── wealthmap.db
        └── attachments/
```

**Backup**: Settings → Backup DB saves a copy of the current profile's
`wealthmap.db` wherever you choose.
**Export**: Settings → Export CSV dumps the current profile's transactions to
a spreadsheet.

---

## ☁️ Google Drive Backup & Restore

Settings → **Backup & Sync** can back up your *entire* data root (every
profile — databases and attachments, not just the one you're currently in)
straight to your own Google Drive, encrypted, so you can pick everything back
up on a new PC. This talks to Google Drive directly (like WhatsApp backing up
to Drive on Android) — it does **not** require the Google Drive desktop app.

**One-time setup — create your own Google OAuth client** (WealthMap doesn't
ship a shared one, so this step is required once, by you):

1. Go to [console.cloud.google.com](https://console.cloud.google.com/) and
   create a new project (any name).
2. **APIs & Services → Library** → enable the **Google Drive API**.
3. **APIs & Services → OAuth consent screen** → choose **External**, fill in
   an app name/support email, and add yourself as a test user.
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   → application type **Desktop app**.
5. Download the resulting JSON file (it's your `client_secret.json`) and keep
   it somewhere you can find again — you'll need the *same* file if you ever
   reconnect on another computer.

**Then in WealthMap**: Settings → Backup & Sync → **Connect Google Drive**
(pick that JSON file, sign in when your browser opens) → **Set Password**
(this encrypts every backup; WealthMap never stores it) → tick which
triggers you want (data changes / once a day / on close — any combination)
→ **Save**.

**Restoring on a new PC**: on the profile picker screen (before opening any
profile), click **Restore from Google Drive**, sign in with the same
`client_secret.json`, pick a backup, and enter your backup password. Nothing
needs to exist locally beforehand — the password is all that's required.

---

## 🔮 Roadmap (Future Versions)

- **v4**: Optional encrypted DB, password lock
- **v5**: ✅ Cloud sync (Google Drive) — see above
- **v6**: Mobile companion app
- **v7**: Budget planning & goal tracking
- **v8**: AI-powered spending insights

---

## 🛠️ Built With

- **Python 3.11+**
- **CustomTkinter** — modern light/dark UI
- **SQLAlchemy** — ORM & database management
- **SQLite** — embedded, zero-config local database
- **yfinance** — live stock/ETF/bond/fund/commodity/crypto prices
- **CoinGecko** — crypto price fallback
- **exchangerate-api.com** — free live exchange rates

---

*WealthMap v3.0 — Local Edition*
