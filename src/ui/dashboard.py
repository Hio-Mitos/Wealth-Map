"""
WealthMap – Dashboard Panel
At-a-glance overview: net worth, recent transactions, account balances, portfolio health.
"""

import tkinter as tk
import customtkinter as ctk
from datetime import datetime, timezone

from src.ui.widgets import (
    SectionHeader,
    StatCard,
    DataTable,
    fmt_money,
    color_for_amount
)
from src.ui.theme import theme


class DashboardPanel(ctk.CTkFrame):
    def __init__(self, parent, ctx, app):
        super().__init__(parent, fg_color=theme.BG_DARK, corner_radius=0)
        self.ctx = ctx
        self.app = app
        self._build()

    def _build(self):
        # Scroll container
        scroll = ctk.CTkScrollableFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=24, pady=16)
        scroll.grid_columnconfigure((0, 1, 2, 3), weight=1)

        base = self.ctx.settings.get("base_currency", "USD")
        base_cur = self.ctx.currency.get_by_code(base)
        sym = base_cur.symbol if base_cur else ""

        # ── Greeting ──────────────────────────────────────────────────────────
        hour = datetime.now().hour
        greeting = "Good morning" if hour < 12 else ("Good afternoon" if hour < 18 else "Good evening")
        SectionHeader(scroll, f"{greeting} 👋",
                      f"Here's your financial snapshot — {datetime.now().strftime('%A, %d %B %Y')}",
                      btn_text="📄 Generate Reports",
                      btn_cmd=lambda: self.app.navigate("reports"),
                      ).grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 20))

        # ── Top stat cards ────────────────────────────────────────────────────
        try:
            snap = self.ctx.account.net_worth_snapshot(base)
            net_worth = snap["total"]
        except Exception:
            net_worth = 0.0

        try:
            port = self.ctx.portfolio.portfolio_summary(base)
            port_value = port["total_value"]
            port_pnl   = port["total_pnl"]
        except Exception:
            port_value = port_pnl = 0.0

        try:
            loan_sum = self.ctx.loan.summary(base)
            owed_me  = loan_sum["owed_to_me"]
            i_owe    = loan_sum["i_owe"]
        except Exception:
            owed_me  = i_owe = 0.0

        now = datetime.now(timezone.utc)
        try:
            monthly = self.ctx.transaction.monthly_summary(now.year, now.month, base)
            income   = monthly["income"]
            expenses = monthly["expenses"]
            net_flow = monthly["net"]
        except Exception:
            income = expenses = net_flow = 0.0

        cards = [
            ("Net Worth",         fmt_money(net_worth, sym), "Across all accounts — tap for your Wealth Journey",
             theme.GOLD,   "💰", lambda: self.app.navigate("analytics")),
            ("Portfolio Value",   fmt_money(port_value, sym), f"P&L: {fmt_money(port_pnl, sym)} — tap for holdings",
             theme.ACCENT, "📈", lambda: self.app.navigate("portfolio")),
            (f"{now.strftime('%B')} Income",   fmt_money(income, sym),   "This month — tap to view",
             theme.GREEN, "⬆", lambda: self.app.navigate("transactions", initial_type="Income")),
            (f"{now.strftime('%B')} Expenses", fmt_money(expenses, sym), "This month — tap to view",
             theme.RED,   "⬇", lambda: self.app.navigate("transactions", initial_type="Expense")),
        ]
        for i, (lbl, val, sub, color, icon, on_click) in enumerate(cards):
            StatCard(scroll, lbl, val, sub, accent=color, icon=icon, on_click=on_click
                     ).grid(row=1, column=i, padx=(0 if i == 0 else 8, 0), pady=(0, 20), sticky="nsew")

        # ── Money flow bar ────────────────────────────────────────────────────
        flow_frame = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                  border_width=1, border_color=theme.BORDER)
        flow_frame.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(0, 20))
        ctk.CTkLabel(flow_frame, text="MONTHLY CASH FLOW",
                     font=("Segoe UI", 10, "bold"), text_color=theme.TEXT_SEC).pack(anchor="w", padx=16, pady=(12, 4))
        bar_outer = ctk.CTkFrame(flow_frame, fg_color=theme.BORDER, corner_radius=6, height=14)
        bar_outer.pack(fill="x", padx=16, pady=(0, 8))
        bar_outer.pack_propagate(False)
        total = income + expenses if (income + expenses) > 0 else 1
        inc_pct = income / total
        bar_inner = ctk.CTkFrame(bar_outer, fg_color=theme.GREEN, corner_radius=6, height=14)
        bar_inner.place(relwidth=inc_pct, relheight=1.0)
        ctk.CTkLabel(flow_frame,
                     text=f"Net: {fmt_money(net_flow, sym)}  •  Saved {inc_pct*100:.1f}% of income",
                     font=("Segoe UI", 11), text_color=theme.TEXT_SEC).pack(anchor="w", padx=16, pady=(0, 12))

        # ── Two-column lower section ──────────────────────────────────────────
        scroll.grid_columnconfigure((0, 1), weight=1)

        left_col  = ctk.CTkFrame(scroll, fg_color="transparent")
        right_col = ctk.CTkFrame(scroll, fg_color="transparent")
        left_col.grid( row=3, column=0, columnspan=2, sticky="nsew", padx=(0, 8), pady=(0, 20))
        right_col.grid(row=3, column=2, columnspan=2, sticky="nsew", padx=(8, 0), pady=(0, 20))

        self._build_accounts_list(left_col, snap, sym)
        self._build_recent_tx(right_col, sym, base)

        # ── Loans & person-to-person row ──────────────────────────────────────
        self._build_loans_summary(scroll, owed_me, i_owe, sym, base)

    def _build_accounts_list(self, parent, snap, sym):
        card = ctk.CTkFrame(parent, fg_color=theme.BG_CARD, corner_radius=12,
                            border_width=1, border_color=theme.BORDER)
        card.pack(fill="both", expand=True)
        ctk.CTkLabel(card, text="ACCOUNTS",
                     font=("Segoe UI", 10, "bold"), text_color=theme.TEXT_SEC).pack(anchor="w", padx=16, pady=(12, 4))
        for acc in snap.get("accounts", []):
            row = ctk.CTkFrame(card, fg_color="transparent", cursor="hand2")
            row.pack(fill="x", padx=12, pady=3)
            dot = ctk.CTkFrame(row, width=10, height=10, corner_radius=5,
                               fg_color=acc.get("color", theme.ACCENT))
            dot.pack(side="left", padx=(4, 8), pady=0)
            dot.pack_propagate(False)
            name_lbl = ctk.CTkLabel(row, text=acc["name"],
                         font=("Segoe UI", 12), text_color=theme.TEXT_PRI,
                         anchor="w")
            name_lbl.pack(side="left", fill="x", expand=True)
            bal_lbl = ctk.CTkLabel(row, text=fmt_money(acc["balance"], acc.get("currency", "")),
                         font=("Segoe UI", 12), text_color=theme.TEXT_SEC, anchor="e")
            bal_lbl.pack(side="right")
            base_lbl = ctk.CTkLabel(row, text=fmt_money(acc["balance_base"], sym),
                         font=("Segoe UI", 12, "bold"), text_color=theme.ACCENT, anchor="e")
            base_lbl.pack(side="right", padx=(0, 12))
            handler = lambda e, n=acc["name"]: self.app.navigate("transactions", initial_account=n)
            for w in (row, dot, name_lbl, bal_lbl, base_lbl):
                w.bind("<Button-1>", handler)
        ctk.CTkLabel(card, text="", height=8).pack()

    def _build_recent_tx(self, parent, sym, base):
        card = ctk.CTkFrame(parent, fg_color=theme.BG_CARD, corner_radius=12,
                            border_width=1, border_color=theme.BORDER)
        card.pack(fill="both", expand=True)
        ctk.CTkLabel(card, text="RECENT TRANSACTIONS",
                     font=("Segoe UI", 10, "bold"), text_color=theme.TEXT_SEC).pack(anchor="w", padx=16, pady=(12, 4))

        from src.models.database import TransactionType, CREDIT_TRANSACTION_TYPES
        txs = self.ctx.transaction.get_recent(15)
        for tx in txs:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=3)
            is_income = tx.transaction_type in CREDIT_TRANSACTION_TYPES or (
                tx.transaction_type == TransactionType.ADJUSTMENT and tx.amount >= 0)
            sign = "+" if is_income else "−"
            color = theme.GREEN if is_income else theme.RED
            ctk.CTkLabel(row, text=sign, font=("Segoe UI", 14, "bold"),
                         text_color=color, width=16).pack(side="left")
            ctk.CTkLabel(row, text=tx.description or tx.category,
                         font=("Segoe UI", 12), text_color=theme.TEXT_PRI,
                         anchor="w").pack(side="left", fill="x", expand=True, padx=4)
            ctk.CTkLabel(row, text=tx.transaction_date.strftime("%d %b"),
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC).pack(side="right", padx=(0, 8))
            amt_str = fmt_money(tx.amount, tx.currency.symbol if tx.currency else "")
            ctk.CTkLabel(row, text=amt_str, font=("Segoe UI", 12, "bold"),
                         text_color=color, anchor="e").pack(side="right")
        if not txs:
            ctk.CTkLabel(card, text="No transactions yet",
                         text_color=theme.TEXT_SEC, font=("Segoe UI", 12)).pack(pady=20)
        ctk.CTkLabel(card, text="", height=8).pack()

    def _build_loans_summary(self, parent, owed_me, i_owe, sym, base):
        frame = ctk.CTkFrame(parent, fg_color=theme.BG_CARD, corner_radius=12,
                             border_width=1, border_color=theme.BORDER)
        frame.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(0, 20))
        ctk.CTkLabel(frame, text="PERSONAL LOANS & DEBTS",
                     font=("Segoe UI", 10, "bold"), text_color=theme.TEXT_SEC).pack(anchor="w", padx=16, pady=(12, 8))
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 12))
        for label, val, col in [
            ("Owed to me", owed_me, theme.GREEN),
            ("I owe", i_owe, theme.RED),
            ("Net position", owed_me - i_owe, theme.GOLD),
        ]:
            box = ctk.CTkFrame(row, fg_color=theme.BG_HOVER, corner_radius=8, cursor="hand2")
            box.pack(side="left", padx=(0, 12), ipadx=20, ipady=8)
            lbl1 = ctk.CTkLabel(box, text=label, font=("Segoe UI", 10), text_color=theme.TEXT_SEC)
            lbl1.pack(padx=16, pady=(8, 2))
            lbl2 = ctk.CTkLabel(box, text=fmt_money(val, sym), font=("Segoe UI", 16, "bold"),
                         text_color=col)
            lbl2.pack(padx=16, pady=(2, 8))
            handler = lambda e: self.app.navigate("loans")
            for w in (box, lbl1, lbl2):
                w.bind("<Button-1>", handler)
