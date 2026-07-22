"""
WealthMap – Taxes Panel

Surfaces every tax paid across the app in one place — Tax-type
transactions (e.g. WTAX deductions imported from a payslip), the
primary tax_amount field on any transaction, and any additional
tax-kind TransactionCharge line — so "how much tax have I paid" has a
single answer, filterable by date range, with click-through to the
full transaction record.
"""

from datetime import datetime
from tkinter import messagebox
import customtkinter as ctk

from src.models.database import Transaction, TransactionType
from src.ui.widgets import SectionHeader, StatCard, DataTable, fmt_money_base
from src.ui.theme import theme
from src.ui.transaction_dialog import open_transaction_modal


class TaxesPanel(ctk.CTkFrame):
    def __init__(self, parent, ctx, app):
        super().__init__(parent, fg_color=theme.BG_DARK, corner_radius=0)
        self.ctx = ctx
        self.app = app
        self._start_date = None
        self._end_date = None
        self._build()

    def _build(self):
        base = self.ctx.settings.get("base_currency", "USD")
        base_cur = self.ctx.currency.get_by_code(base)
        self._sym = base_cur.symbol if base_cur else ""
        self._base = base

        scroll = ctk.CTkScrollableFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=24, pady=16)
        scroll.grid_columnconfigure(0, weight=1)

        SectionHeader(scroll, "Taxes",
                      "Every tax paid across every transaction, deduction, and payslip",
                      "＋ New Tax Payment", self._open_new_tax
                      ).grid(row=0, column=0, sticky="ew", pady=(0, 16))

        self._cards_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self._cards_frame.grid(row=1, column=0, sticky="ew", pady=(0, 16))

        # Date-range filter
        filter_bar = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=10,
                                  border_width=1, border_color=theme.BORDER)
        filter_bar.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(filter_bar, text="Period:", text_color=theme.TEXT_SEC,
                     font=("Segoe UI", 12)).pack(side="left", padx=(12, 8), pady=10)
        self._start_e = ctk.CTkEntry(filter_bar, placeholder_text="YYYY-MM-DD (from)", width=140)
        self._start_e.pack(side="left", padx=4, pady=8)
        self._end_e = ctk.CTkEntry(filter_bar, placeholder_text="YYYY-MM-DD (to)", width=140)
        self._end_e.pack(side="left", padx=4, pady=8)
        ctk.CTkButton(filter_bar, text="Apply", width=70, height=32,
                      fg_color=theme.ACCENT, hover_color=theme.BG_SELECTED, text_color="#fff",
                      font=("Segoe UI", 11), command=self._apply_period).pack(side="left", padx=4)
        ctk.CTkButton(filter_bar, text="Clear", width=70, height=32,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.TEXT_SEC, font=("Segoe UI", 11),
                      command=self._clear_period).pack(side="left", padx=4)
        self._count_label = ctk.CTkLabel(filter_bar, text="",
                                          text_color=theme.TEXT_SEC, font=("Segoe UI", 11))
        self._count_label.pack(side="right", padx=12)

        cols = [
            {"key": "date",        "label": "Date",        "width": 90,  "anchor": "w"},
            {"key": "account",     "label": "Account",     "width": 120, "anchor": "w"},
            {"key": "description", "label": "Description", "width": 200, "anchor": "w"},
            {"key": "source",      "label": "Source",       "width": 130, "anchor": "w"},
            {"key": "amount",      "label": "Amount",       "width": 110, "anchor": "e"},
            {"key": "currency",    "label": "CCY",          "width": 50,  "anchor": "w"},
        ]
        self._table = DataTable(scroll, cols, height=420)
        self._table.grid(row=3, column=0, sticky="nsew", pady=(0, 8))

        self._load()

    # ── Filtering ─────────────────────────────────────────────────────────

    def _apply_period(self):
        def parse(text):
            text = (text or "").strip()
            if not text:
                return None
            return datetime.strptime(text, "%Y-%m-%d")
        try:
            self._start_date = parse(self._start_e.get())
            self._end_date = parse(self._end_e.get())
        except ValueError:
            messagebox.showerror("Invalid Date", "Use the format YYYY-MM-DD.", parent=self)
            return
        self._load()

    def _clear_period(self):
        self._start_date = None
        self._end_date = None
        self._start_e.delete(0, "end")
        self._end_e.delete(0, "end")
        self._load()

    # ── Data gathering ────────────────────────────────────────────────────

    def _in_range(self, dt) -> bool:
        if self._start_date and dt < self._start_date:
            return False
        if self._end_date and dt > self._end_date:
            return False
        return True

    def _gather_tax_rows(self):
        """One row per distinct tax amount: a TAX-type transaction's full
        amount, a transaction's primary tax_amount field, and any tax-kind
        TransactionCharge — each independently, since they represent
        separate figures even when they land on the same transaction."""
        txs = self.ctx.session.query(Transaction).all()
        txs = [tx for tx in txs if self._in_range(tx.transaction_date)]

        rows = []
        for tx in txs:
            cur = tx.currency
            sym = cur.symbol if cur else ""
            code = cur.code if cur else self._base

            if tx.transaction_type == TransactionType.TAX:
                rows.append(self._row(tx, tx.description or "Tax Payment", "Tax Transaction",
                                      tx.amount, code, sym))
            if tx.tax_amount:
                rows.append(self._row(tx, tx.tax_description or tx.description or "Tax",
                                      "Transaction Tax Field", tx.tax_amount,
                                      (tx.tax_currency or cur).code if (tx.tax_currency or cur) else code,
                                      (tx.tax_currency or cur).symbol if (tx.tax_currency or cur) else sym))
            for charge in tx.charges:
                if charge.kind != "tax":
                    continue
                c_cur = charge.currency or cur
                rows.append(self._row(tx, charge.description or "Tax Charge", "Charge Line",
                                      charge.amount, c_cur.code if c_cur else code,
                                      c_cur.symbol if c_cur else sym))
        rows.sort(key=lambda r: r["_tx_obj"].transaction_date, reverse=True)
        return rows

    def _row(self, tx, description, source, amount, currency_code, sym):
        return {
            "date":        tx.transaction_date.strftime("%d %b %Y"),
            "account":     tx.account.name if tx.account else "—",
            "description": description or "—",
            "source":      source,
            "amount":      f"{sym}{amount:,.2f}",
            "currency":    currency_code,
            "_tx_obj":     tx,
            "_base_amount": self.ctx.currency.convert(amount, currency_code, self._base) or amount,
        }

    def _load(self):
        rows = self._gather_tax_rows()
        self._table.set_rows(rows, on_select=self._on_row_select)
        self._count_label.configure(text=f"{len(rows)} tax records")

        total_base = sum(r["_base_amount"] for r in rows)
        count_txs = len({r["_tx_obj"].id for r in rows})
        for w in self._cards_frame.winfo_children():
            w.destroy()
        for i in range(2):
            self._cards_frame.grid_columnconfigure(i, weight=1)
        StatCard(self._cards_frame, "Total Taxes Paid",
                 fmt_money_base(self.ctx, total_base, self._base), "", theme.RED, "🏛️"
                 ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        StatCard(self._cards_frame, "Transactions Involved", str(count_txs), "", theme.ACCENT, "🧾"
                 ).grid(row=0, column=1, sticky="ew")

    def _on_row_select(self, row):
        tx = row.get("_tx_obj")
        if tx:
            open_transaction_modal(self, self.ctx, self.app, tx,
                                   on_saved=lambda *a: self._load(),
                                   on_deleted=self._load)

    def _open_new_tax(self):
        open_transaction_modal(self, self.ctx, self.app, on_saved=lambda *a: (self.app.refresh(), self._load()))
